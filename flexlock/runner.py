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
    enqueue_to_file,
)
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
        parser.add_argument(
            "--check",
            action="store_true",
            help="Preflight: fully resolve the config (and every sweep item) "
            "without touching the filesystem or executing. Reports every "
            "unresolved interpolation with its key, then exits.",
        )
        parser.add_argument(
            "--dump",
            action="store_true",
            help="Print the compiled configuration as clean YAML and exit (no headers). "
                 "Redirect to a file to capture it for later use with --sweep-file or --enqueue.",
        )
        parser.add_argument(
            "--edit-config", "-e",
            action="store_true",
            help="Open the compiled configuration in $EDITOR before running. "
                 "Like 'git commit': edit the YAML, save and quit to proceed.",
        )
        parser.add_argument(
            "--enqueue",
            metavar="FILE",
            help="Append the compiled configuration to a YAML queue file and exit. "
                 "Creates the file if it does not exist. Run the queue later with "
                 "--sweep-file FILE.",
        )

        # Existing Config/Select args
        parser.add_argument(
            "--defaults", "-d", help="Python import path for default config"
        )
        parser.add_argument("--config", "-c", help="Path to base YAML config file")
        parser.add_argument(
            "--select",
            "-s",
            nargs="+",
            help="Dot-separated key selecting the node to run. Pass several "
            "(space- or comma-separated, e.g. '-s train linear_probe' or "
            "'-s train,linear_probe') to run stages in order. Multi-stage is "
            "incompatible with -O/-M, sweeps, and HPC backends (run those "
            "stages one at a time).",
        )

        # Existing Override args
        parser.add_argument("--merge", "-m", help="Merge file into Root config")
        parser.add_argument(
            "--overrides",
            "-o",
            nargs="+",
            action="append",
            default=[],
            help="Dot-list overrides for Root config (repeatable: -o a=1 b=2  or  -o a=1 -o b=2)",
        )
        parser.add_argument(
            "--merge-after-select", "-M", help="Merge file into Selected config"
        )
        parser.add_argument(
            "--overrides-after-select",
            "-O",
            nargs="+",
            action="append",
            default=[],
            help="Dot-list overrides for Selected config (repeatable)",
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
            nargs="+",
            metavar="FILE",
            help="One or more files (yaml, json, txt) providing sweep tasks. "
                 "Each file may contain a single config dict (one task) or a list "
                 "of dicts (multiple tasks). Results are concatenated in order.",
        )
        source.add_argument(
            "--sweep",
            help="Comma-separated values (e.g. '0.01,0.02' or 'lr=0.1,lr=0.2')",
        )

        # Sweep root override
        sweep_group.add_argument(
            "--sweep-root",
            metavar="DIR",
            help="Override the directory used as the sweep root for the tasks DB "
                 "and lineage markers. Use this when your sweep items have pre-set "
                 "save_dirs that don't nest under the base config's save_dir.",
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
        parser.add_argument(
            "--note",
            metavar="TEXT",
            help="Free-text intent recorded as a top-level 'note:' key in run.lock "
                 "(e.g. --note 'baseline before lr sweep'). Never affects caching. "
                 "For sweeps the note lands on the master run.lock.",
        )
        parser.add_argument(
            "--save-dir-policy",
            choices=["increment", "timestamp"],
            default=None,
            help="Derive the concrete run directory from save_dir at submit "
            "time: 'increment' versions it (run -> run_0000, claimed "
            "atomically); 'timestamp' appends the timestamp format. Replaces "
            "the ${vinc:}/${now:} resolvers.",
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

    @staticmethod
    def _flatten_overrides(value):
        """Normalize ``--overrides``/``-o`` into a flat list of ``key=value``.

        Because the argument uses ``nargs="+"`` plus ``action="append"`` to be
        repeatable (``-o a=1 b=2`` and ``-o a=1 -o b=2``), argparse yields a
        list of lists. This collapses it to the flat list OmegaConf expects.
        Idempotent: an already-flat list of strings passes through unchanged.
        """
        if not value:
            return []
        flat = []
        for item in value:
            if isinstance(item, str):
                flat.append(item)
            else:  # a group produced by action="append"
                flat.extend(item)
        return flat

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
        overrides = self._flatten_overrides(args.overrides)
        if overrides:
            cfg.merge_with(OmegaConf.from_dotlist(overrides))

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

    @staticmethod
    def _parse_selects(value) -> List:
        """Normalize ``--select``/``-s`` into a flat list of stage keys.

        ``--select`` uses ``nargs="+"`` so space-separated stages arrive as a
        list; each entry may also be comma-separated. Returns ``[None]`` when
        no selection was given (the whole root config is the node).
        """
        if not value:
            return [None]
        keys = []
        for item in value:
            for part in str(item).split(","):
                part = part.strip()
                if part:
                    keys.append(part)
        return keys or [None]

    def _validate_multiselect(self, args):
        """Reject flags whose meaning is ambiguous with a stage *sequence*.

        Phase 1 keeps multi-stage strictly local + sequential. After-select
        overrides target *the* selected node (undefined with many), sweeps and
        HPC backends need a defined cross-stage semantic that isn't wired yet.
        Root-level ``-o``/``-m``/``-c`` remain valid — that's how you pass a
        shared anchor like ``pipeline_dir``.
        """
        offending = []
        if args.overrides_after_select:
            offending.append("-O/--overrides-after-select")
        if args.merge_after_select:
            offending.append("-M/--merge-after-select")
        if args.sweep or args.sweep_file or args.sweep_key:
            offending.append("--sweep/--sweep-file/--sweep-key")
        if getattr(args, "slurm_config", None) or getattr(args, "pbs_config", None):
            offending.append("--slurm-config/--pbs-config")
        if args.enqueue:
            offending.append("--enqueue")
        if args.edit_config:
            offending.append("-e/--edit-config")
        if offending:
            raise FlexLockValidationError(
                "Multi-stage selection (-s with >1 stage) is incompatible with: "
                + ", ".join(offending)
                + ". Run these stages one at a time, or pass shared values as "
                "root-level overrides (-o pipeline_dir=..., -m, -c)."
            )

    def _build_node_cfg(self, args, root_cfg, base_cfg, select, name=None):
        """Select a node from ``root_cfg`` and prepare it for submission.

        Mirrors the single-stage path (selection → base_cfg mutual-merge →
        save_dir default) so each stage in a sequence is built identically.
        """
        if select:
            try:
                node_cfg = select_and_freeze_root_refs(root_cfg, select)
            except KeyError as e:
                raise FlexLockValidationError(
                    f"Selection '{select}' returned None."
                ) from e
        else:
            node_cfg = root_cfg

        if base_cfg is not None:
            _b = base_cfg.copy()
            _b.merge_with(node_cfg)
            node_cfg.merge_with(_b)

        return self._prepare_node(node_cfg, name=name or select or "exp")

    def _run_multi(self, args, root_cfg, base_cfg, selects):
        """Run a sequence of selected stages in order, locally and blocking.

        Each stage is an independent :meth:`Project.submit` with ``wait=True``,
        so downstream stages see upstream artifacts on disk (the ``pipeline_dir``
        anchor pattern). Returns the list of raw stage return values.
        """
        from .api import Project

        self._validate_multiselect(args)
        debug = args.debug or config.get_env_bool("FLEXLOCK_DEBUG", False)
        proj = Project(root_cfg)

        results = []
        for sel in selects:
            node_cfg = self._build_node_cfg(args, root_cfg, base_cfg, sel)

            # Preview flags iterate over the whole sequence rather than submit.
            if args.print_config:
                print(f"# --- stage: {sel} ---")
                self._print_config_and_docstring(node_cfg)
                continue
            if args.dump:
                print(f"# --- stage: {sel} ---")
                print(OmegaConf.to_yaml(node_cfg), end="")
                continue

            logger.info(
                f"[multi-select] stage '{sel}' → {node_cfg.get('save_dir')}"
            )
            outcome = proj.submit(
                node_cfg,
                n_jobs=args.n_jobs,
                smart_run=bool(args.check_exists),
                debug=debug,
                print_config=False,
                dry_run=getattr(args, "dry_run", False),
                note=getattr(args, "note", None),
                save_dir_policy=getattr(args, "save_dir_policy", None),
            )
            results.append(outcome)

        if args.print_config or args.dump:
            return None
        return [r.result if hasattr(r, "result") else r for r in results]

    def _prepare_node(self, cfg, name="exp"):
        """Ensure ``cfg`` has a ``save_dir`` — fall back to ``outputs/<name>/<timestamp>``."""
        if "save_dir" not in cfg or cfg.save_dir is None:
            ts = datetime.now().strftime(config.TIMESTAMP_FORMAT)
            with open_dict(cfg):
                cfg.save_dir = str(Path("outputs") / name / ts)
        cfg.save_dir = cfg.save_dir  # Force interpolation resolution
        return cfg

    def run(self, cli_args=None, base_cfg=None):
        """Thin layer over :meth:`Project.submit` — shapes CLI args and dispatches."""
        from .api import Project

        args = self.parser.parse_args(cli_args)
        args.overrides = self._flatten_overrides(args.overrides)
        args.overrides_after_select = self._flatten_overrides(args.overrides_after_select)

        # `--help` / `-h` is registered with action='store_true' (we own
        # help formatting), so argparse parses but doesn't auto-exit. We
        # honour it here before doing any work.
        if args.help:
            self.parser.print_help()
            return None

        # Build the root config from CLI inputs (defaults + config + merge + overrides).
        root_cfg = self.load_config(args)
        logger.info(f"Loaded root config: {root_cfg}")

        # Normalize -s into a list of stage keys. Several stages run in order
        # via the multi-stage path; a single stage keeps the original flow.
        selects = self._parse_selects(args.select)
        if len(selects) > 1:
            return self._run_multi(args, root_cfg, base_cfg, selects)
        select = selects[0]

        # Selection happens at the node level — freezes root-scope refs.
        if select:
            try:
                node_cfg = select_and_freeze_root_refs(root_cfg, select)
            except KeyError as e:
                raise FlexLockValidationError(
                    f"Selection '{select}' returned None."
                ) from e
            # Warn when a -o key also exists in the selected subtree — the
            # override landed on the root, not the stage. Root-only anchors
            # (params, pipeline_dir, …) are intentional and stay silent.
            if args.overrides:
                _missing = object()
                for kv in args.overrides:
                    key = kv.split("=", 1)[0]
                    if OmegaConf.select(node_cfg, key, default=_missing) is not _missing:
                        logger.warning(
                            f"'-o {kv}' was applied to the root config, but key '{key}' "
                            f"also exists in the selected node '{select}' — "
                            f"your override did NOT reach the stage. "
                            f"Use '-O {kv}' to override the stage directly. "
                            f"See docs/cli_reference.md § Configuration Overrides."
                        )
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

        # --edit-config / -e: open compiled config in $EDITOR before running.
        if args.edit_config:
            import subprocess
            import tempfile
            editor = os.environ.get("EDITOR", "vi")
            original_yaml = OmegaConf.to_yaml(node_cfg)
            with tempfile.NamedTemporaryFile(
                suffix=".yaml", mode="w", delete=False, prefix="flexlock_edit_"
            ) as f:
                f.write(original_yaml)
                tmppath = f.name
            try:
                while True:
                    subprocess.call([editor, tmppath])
                    with open(tmppath) as fh:
                        edited_raw = fh.read()
                    try:
                        node_cfg = OmegaConf.create(yaml.safe_load(edited_raw))
                        break
                    except Exception as exc:
                        print(f"[flexlock] Invalid YAML: {exc}")
                        answer = input("Re-open editor? [Y/n] ").strip().lower()
                        if answer in ("n", "no"):
                            raise SystemExit(1)
                if edited_raw == original_yaml:
                    answer = input("No changes detected, run anyway? [y/N] ").strip().lower()
                    if answer not in ("y", "yes"):
                        raise SystemExit(0)
            finally:
                Path(tmppath).unlink(missing_ok=True)

        # --dump: emit clean YAML (no decorative headers) and exit.
        if args.dump:
            print(OmegaConf.to_yaml(node_cfg), end="")
            return None

        # --enqueue: append compiled config to a YAML queue file and exit.
        if args.enqueue:
            cfg_dict = OmegaConf.to_container(node_cfg, resolve=False, throw_on_missing=False)
            n = enqueue_to_file(args.enqueue, cfg_dict)
            logger.info(f"Enqueued 1 task → {args.enqueue} ({n} task(s) in queue)")
            return None

        # Load the sweep list from whichever source the user picked.
        sweep_tasks = load_sweep(
            sweep=args.sweep,
            sweep_file=args.sweep_file,
            sweep_key=args.sweep_key,
            root_cfg=root_cfg,
        )

        # Honour FLEXLOCK_DEBUG env var as a CLI-side debug toggle.
        debug = args.debug or config.get_env_bool("FLEXLOCK_DEBUG", False)

        # Hand off to the single execution kernel.
        proj = Project(root_cfg)

        # --check: side-effect-free preflight resolution, then exit.
        if args.check:
            errors = proj.check(
                node_cfg,
                sweep=sweep_tasks or None,
                sweep_target=args.sweep_target,
                overrides=args.overrides_after_select or None,
                merge=args.merge_after_select,
            )
            if not errors:
                print("[flexlock] check OK — all interpolations resolve.")
                return None
            print(f"[flexlock] check FAILED — {len(errors)} unresolved interpolation(s):")
            for e in errors:
                where = "" if e["item"] is None else f"sweep item {e['item']}, "
                print(f"  - {where}{e['full_key']}: {e['error']}")
            raise SystemExit(1)
        outcome = proj.submit(
            node_cfg,
            sweep=sweep_tasks or None,
            sweep_target=args.sweep_target,
            sweep_root=getattr(args, "sweep_root", None),
            n_jobs=args.n_jobs,
            smart_run=bool(args.check_exists),
            slurm_config=getattr(args, "slurm_config", None),
            pbs_config=getattr(args, "pbs_config", None),
            overrides=args.overrides_after_select or None,
            merge=args.merge_after_select,
            debug=debug,
            print_config=args.print_config,
            dry_run=getattr(args, "dry_run", False),
            note=getattr(args, "note", None),
            save_dir_policy=getattr(args, "save_dir_policy", None),
        )

        # Back-compat: the runner historically returned the user function's
        # raw return value (and is consumed by @flexcli as such). Unwrap the
        # ExecutionResult so existing callers keep working.
        if outcome is None:
            return None
        if isinstance(outcome, list):
            return [r.result if hasattr(r, "result") else r for r in outcome]
        return outcome.result if hasattr(outcome, "result") else outcome
