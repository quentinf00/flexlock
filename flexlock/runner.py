"""Runner for FlexLock experiments."""

import argparse
import yaml
import os
from pathlib import Path
from typing import List, Any, Dict
from omegaconf import OmegaConf, open_dict
from datetime import datetime
from .utils import (
    load_python_defaults,
    py2cfg,
    select_and_freeze_root_refs,
    parse_sweep_string,
    load_sweep,
)
from .diff import RunDiff
from .exceptions import FlexLockValidationError
from . import config
from loguru import logger


class FlexLockRunner:
    def __init__(self):
        self.parser = self._build_parser()

    def _print_config_and_docstring(self, node_cfg):
        """Print compiled config and target docstring."""
        print("=== COMPILED CONFIG ===")
        print(OmegaConf.to_yaml(node_cfg))

        if "_target_" in node_cfg:
            print("=== TARGET FUNCTION DOCSTRING ===")
            try:
                target_path = node_cfg._target_
                module_name, func_name = target_path.rsplit(".", 1)
                module = __import__(module_name, fromlist=[func_name])
                target_func = getattr(module, func_name)
                docstring = getattr(target_func, "__doc__", None)
                print(f"Target: {target_path}")
                print(
                    f"Docstring:\n{docstring}"
                    if docstring
                    else "No docstring available."
                )
            except (ImportError, AttributeError, ValueError) as e:
                print(f"Could not import target function '{node_cfg._target_}': {e}")

    def _build_parser(self):
        parser = argparse.ArgumentParser(
            description="FlexLock Execution Manager", add_help=False
        )

        parser.add_argument(
            "-h", "--help", action="store_true", help="Show this help message and exit."
        )
        parser.add_argument(
            "--print-config",
            action="store_true",
            help="Print the compiled configuration and target function docstring, then exit.",
        )

        # Existing Config/Select args
        parser.add_argument(
            "--defaults", "-d", help="Python import path for default config"
        )
        parser.add_argument("--config", "-c", help="Path to base YAML config file")
        parser.add_argument(
            "--select", "-s", help="Dot-separated key to select the node to run"
        )

        # Existing Override args
        parser.add_argument("--merge", "-m", help="Merge file into Root config")
        parser.add_argument(
            "--overrides",
            "-o",
            nargs="*",
            default=[],
            help="Dot-list overrides for Root config",
        )
        parser.add_argument(
            "--merge-after-select", "-M", help="Merge file into Selected config"
        )
        parser.add_argument(
            "--overrides-after-select",
            "-O",
            nargs="*",
            default=[],
            help="Dot-list overrides for Selected config",
        )

        # NEW SWEEP ARGUMENTS
        sweep_group = parser.add_argument_group("Sweep Configuration")

        # Source (Mutually Exclusive)
        source = sweep_group.add_mutually_exclusive_group()
        source.add_argument(
            "--sweep-key",
            help="Key in config containing the sweep list (e.g. 'experiments.grid')",
        )
        source.add_argument(
            "--sweep-file",
            help="Path to a file (yaml, json, txt) containing the sweep list",
        )
        source.add_argument(
            "--sweep",
            help="Comma-separated values (e.g. '0.01,0.02' or 'lr=0.1,lr=0.2')",
        )

        # Injection Target
        sweep_group.add_argument(
            "--sweep-target",
            help="Dot-path key to inject the sweep value into (e.g. 'optimizer.lr'). "
            "If omitted, sweep items are merged at the root.",
        )

        # Execution
        parser.add_argument(
            "--n_jobs",
            type=int,
            default=config.DEFAULT_N_JOBS,
            help="Number of parallel jobs",
        )
        parser.add_argument(
            "--check-exists",
            action="store_true",
            help="Check if run already exists and skip if so.",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Enable debug mode (Post-mortem PDB in scripts, Locals Injection in Notebooks).",
        )

        # HPC Backend Configuration
        backend_group = parser.add_argument_group("HPC Backend Configuration")
        backend = backend_group.add_mutually_exclusive_group()
        backend.add_argument(
            "--slurm-config",
            help="Path to Slurm configuration YAML file for HPC execution",
        )
        backend.add_argument(
            "--pbs-config", help="Path to PBS configuration YAML file for HPC execution"
        )
        backend_group.add_argument(
            "--dry-run",
            action="store_true",
            help="Render the HPC submission script and exit without submitting "
            "(also prints validation warnings).",
        )

        return parser

    def load_config(self, args):
        # 1. Start with Injected Base (from decorator) or Empty
        cfg = OmegaConf.create()

        # 2. Merge Python Defaults (if --defaults passed)
        # Note: --defaults flag overrides decorator defaults if both exist
        if args.defaults:
            ext_defaults = load_python_defaults(args.defaults)
            cfg.merge_with(OmegaConf.create(ext_defaults))

        # 3. Outer Overrides
        if args.config:
            cfg.merge_with(OmegaConf.load(args.config))
        if args.merge:
            cfg.merge_with(OmegaConf.load(args.merge))
        if args.overrides:
            cfg.merge_with(OmegaConf.from_dotlist(args.overrides))

        if args.debug:
            logger.debug(f"Final Root Config: {cfg}")
        return cfg

    def _parse_cli_sweep(self, sweep_str: str) -> List[Any]:
        """Back-compat shim — delegates to :func:`flexlock.utils.parse_sweep_string`."""
        return parse_sweep_string(sweep_str)

    def _load_sweep_tasks(self, args, root_cfg) -> List[Dict]:
        """Back-compat shim — delegates to :func:`flexlock.utils.load_sweep`."""
        return load_sweep(
            sweep=args.sweep,
            sweep_file=args.sweep_file,
            sweep_key=args.sweep_key,
            root_cfg=root_cfg,
        )

    def _prepare_node(self, cfg, name="exp"):
        """Ensure ``cfg`` has a ``save_dir`` — fall back to ``outputs/<name>/<timestamp>``."""
        if "save_dir" not in cfg or cfg.save_dir is None:
            ts = datetime.now().strftime(config.TIMESTAMP_FORMAT)
            with open_dict(cfg):
                cfg.save_dir = str(Path("outputs") / name / ts)
        cfg.save_dir = cfg.save_dir  # Force interpolation resolution
        return cfg

    def check_if_exists(self, cfg):
        """Check if a run with the same configuration already exists."""
        save_dir = Path(cfg.get("save_dir", "."))
        lock_file = save_dir / "run.lock"

        if not lock_file.exists():
            return False

        # Load existing run data
        with open(lock_file, "r") as f:
            existing_data = yaml.safe_load(f)

        # Compare with current configuration
        diff = RunDiff(cfg, existing_data)
        return diff.is_match()

    def run(self, cli_args=None, base_cfg=None):
        """Thin layer over :meth:`Project.submit` — shapes CLI args and dispatches."""
        from .api import Project

        args = self.parser.parse_args(cli_args)

        # Build the root config from CLI inputs (defaults + config + merge + overrides).
        root_cfg = self.load_config(args)
        logger.info(f"Loaded root config: {root_cfg}")

        # Selection happens at the node level — freezes root-scope refs.
        if args.select:
            try:
                node_cfg = select_and_freeze_root_refs(root_cfg, args.select)
            except KeyError as e:
                raise FlexLockValidationError(
                    f"Selection '{args.select}' returned None."
                ) from e
        else:
            node_cfg = root_cfg

        # @flexcli decorator may inject a base_cfg — preserve the existing
        # mutual-merge semantics so global keys keep their root pointers.
        if base_cfg is not None:
            _b = base_cfg.copy()
            _b.merge_with(node_cfg)
            node_cfg.merge_with(_b)

        # Inject a default save_dir if the selected node doesn't carry one.
        node_cfg = self._prepare_node(node_cfg)

        # Load the sweep list from whichever source the user picked.
        sweep_tasks = load_sweep(
            sweep=args.sweep,
            sweep_file=args.sweep_file,
            sweep_key=args.sweep_key,
            root_cfg=root_cfg,
        )

        # Honour FLEXLOCK_DEBUG env var as a CLI-side debug toggle.
        debug = args.debug or os.environ.get("FLEXLOCK_DEBUG", "false").lower() in (
            "1",
            "true",
        )

        # Hand off to the single execution kernel.
        proj = Project(root_cfg)
        outcome = proj.submit(
            node_cfg,
            sweep=sweep_tasks or None,
            sweep_target=args.sweep_target,
            n_jobs=args.n_jobs,
            smart_run=bool(args.check_exists),
            slurm_config=getattr(args, "slurm_config", None),
            pbs_config=getattr(args, "pbs_config", None),
            overrides=args.overrides_after_select or None,
            merge=args.merge_after_select,
            debug=debug,
            print_config=args.print_config,
            dry_run=getattr(args, "dry_run", False),
        )

        # Back-compat: the runner historically returned the user function's
        # raw return value (and is consumed by @flexcli as such). Unwrap the
        # ExecutionResult so existing callers keep working.
        if outcome is None:
            return None
        if isinstance(outcome, list):
            return [r.result if hasattr(r, "result") else r for r in outcome]
        return outcome.result if hasattr(outcome, "result") else outcome
