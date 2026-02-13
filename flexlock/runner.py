"""Runner for FlexLock experiments."""

import argparse
import json
import csv
import yaml
import os
from pathlib import Path
from typing import List, Any, Dict
from omegaconf import OmegaConf, open_dict, ListConfig, DictConfig
from datetime import datetime
from .utils import load_python_defaults, instantiate, py2cfg, extract_tracking_info
from .debug import debug_on_fail
from .parallel import ParallelExecutor
from .snapshot import snapshot
from .diff import RunDiff
from .exceptions import FlexLockValidationError, FlexLockConfigError
from . import config
from loguru import logger


class FlexLockRunner:
    def __init__(self):
        self.parser = self._build_parser()

    def _build_parser(self):
        parser = argparse.ArgumentParser(description="FlexLock Execution Manager")

        # Existing Config/Select args
        parser.add_argument(
            "--defaults", "-d", 
            help="Python import path for default config"
        )
        parser.add_argument(
            "--config", "-c",
            help="Path to base YAML config file"
        )
        parser.add_argument(
            "--select", "-s",
            help="Dot-separated key to select the node to run"
        )

        # Existing Override args
        parser.add_argument(
            "--merge", "-m",
            help="Merge file into Root config"
        )
        parser.add_argument(
            "--overrides", "-o", nargs="*", default=[],
            help="Dot-list overrides for Root config"
        )
        parser.add_argument(
            "--merge-after-select", "-M",
            help="Merge file into Selected config"
        )
        parser.add_argument(
            "--overrides-after-select", "-O", nargs="*", default=[],
            help="Dot-list overrides for Selected config"
        )

        # NEW SWEEP ARGUMENTS
        sweep_group = parser.add_argument_group("Sweep Configuration")

        # Source (Mutually Exclusive)
        source = sweep_group.add_mutually_exclusive_group()
        source.add_argument("--sweep-key", help="Key in config containing the sweep list (e.g. 'experiments.grid')")
        source.add_argument("--sweep-file", help="Path to a file (yaml, json, txt) containing the sweep list")
        source.add_argument("--sweep", help="Comma-separated values (e.g. '0.01,0.02' or 'lr=0.1,lr=0.2')")

        # Injection Target
        sweep_group.add_argument(
            "--sweep-target",
            help="Dot-path key to inject the sweep value into (e.g. 'optimizer.lr'). "
                 "If omitted, sweep items are merged at the root."
        )

        # Execution
        parser.add_argument("--n_jobs", type=int, default=config.DEFAULT_N_JOBS, help="Number of parallel jobs")
        parser.add_argument(
            "--check-exists", action="store_true",
            help="Check if run already exists and skip if so."
        )
        parser.add_argument(
            "--debug", action="store_true",
            help="Enable debug mode (Post-mortem PDB in scripts, Locals Injection in Notebooks)."
        )

        parser.add_argument(
            "--print-config", action="store_true",
            help="Print the compiled configuration and target function docstring when available."
        )

        # HPC Backend Configuration
        backend_group = parser.add_argument_group("HPC Backend Configuration")
        backend = backend_group.add_mutually_exclusive_group()
        backend.add_argument(
            "--slurm-config",
            help="Path to Slurm configuration YAML file for HPC execution"
        )
        backend.add_argument(
            "--pbs-config",
            help="Path to PBS configuration YAML file for HPC execution"
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
        """
        Parse comma-separated sweep values from CLI.

        Handles:
        - Simple values: "1,2,3" → [1, 2, 3]
        - Key=value pairs: "lr=0.1,lr=0.2" → [{'lr': 0.1}, {'lr': 0.2}]
        - Quoted strings: '"a,b",c' → ['a,b', 'c']

        Args:
            sweep_str: Comma-separated sweep values

        Returns:
            List of parsed values (int, float, dict, or str)

        Examples:
            >>> _parse_cli_sweep("1,2,3")
            [1, 2, 3]
            >>> _parse_cli_sweep("lr=0.1,lr=0.2")
            [{'lr': 0.1}, {'lr': 0.2}]
        """
        # Use csv reader to handle quoted strings correctly
        reader = csv.reader([sweep_str], skipinitialspace=True)
        items = next(reader)

        parsed_items = []
        for item in items:
            # Check for "key=value" format to support simple dict overrides
            if "=" in item:
                # This returns a DictConfig
                try:
                    conf = OmegaConf.from_dotlist([item])
                    # Convert to primitive dict
                    parsed_items.append(OmegaConf.to_container(conf))
                except Exception:
                    # Fallback to string if parsing fails
                    parsed_items.append(item)
            else:
                # Try to cast to int/float/bool, fallback to string
                try:
                    # YAML safe load handles typing (1 -> int, 1.0 -> float, true -> bool)
                    val = yaml.safe_load(item)
                    parsed_items.append(val)
                except Exception:
                    parsed_items.append(item)
        return parsed_items

    def _load_sweep_tasks(self, args, root_cfg) -> List[Dict]:
        """
        Extracts and normalizes the sweep list based on CLI arguments.
        Returns a list of Dictionaries (Tasks).

        Raises:
            FlexLockValidationError: If multiple sweep sources are provided
        """
        # Validate mutual exclusivity of sweep sources
        sources_provided = sum([
            args.sweep_key is not None,
            args.sweep_file is not None,
            args.sweep is not None
        ])

        if sources_provided > 1:
            raise FlexLockValidationError(
                "Multiple sweep sources provided. "
                "Use only ONE of: --sweep-key, --sweep-file, or --sweep"
            )

        raw_tasks = None

        # 1. Determine Source
        if args.sweep_key:
            raw_tasks = OmegaConf.select(root_cfg, args.sweep_key)
            if raw_tasks is None:
                raise FlexLockValidationError(
                    f"Sweep key '{args.sweep_key}' not found in config."
                )
            # Convert ListConfig to primitive list
            if isinstance(raw_tasks, (ListConfig, DictConfig)):
                raw_tasks = OmegaConf.to_container(raw_tasks, resolve=True)

        elif args.sweep_file:
            fpath = Path(args.sweep_file)
            if not fpath.exists():
                raise FlexLockConfigError(
                    f"Sweep file '{fpath}' not found."
                )

            if fpath.suffix in ['.yaml', '.yml']:
                raw_tasks = OmegaConf.to_container(OmegaConf.load(fpath), resolve=True)
            elif fpath.suffix == '.json':
                with open(fpath) as f:
                    raw_tasks = json.load(f)
            else:
                # Text file: Assume one value per line
                with open(fpath) as f:
                    # strip whitespace and skip empty lines
                    raw_tasks = [line.strip() for line in f if line.strip()]
                    # Attempt type conversion via YAML
                    raw_tasks = [yaml.safe_load(t) for t in raw_tasks]

        elif args.sweep:
            raw_tasks = self._parse_cli_sweep(args.sweep)

        if raw_tasks is None:
            return []

        # Ensure raw_tasks is a list (handle single dict/value case if user messed up config)
        if not isinstance(raw_tasks, list):
            raw_tasks = [raw_tasks]

        return raw_tasks

    def _prepare_node(self, cfg, name="exp"):
        """
        Prepare node config by ensuring it has a save_dir.

        If save_dir is missing or None, generates a timestamped directory
        path: outputs/{name}/{timestamp}

        Args:
            cfg: Configuration node to prepare
            name: Name prefix for auto-generated save_dir (default: "exp")

        Returns:
            DictConfig: Updated configuration with save_dir set
        """
        # Inject save_dir if missing
        if "save_dir" not in cfg or cfg.save_dir is None:
             ts = datetime.now().strftime(config.TIMESTAMP_FORMAT)
             path = Path("outputs") / name / ts
             with open_dict(cfg):
                 cfg.save_dir = str(path)
        cfg.save_dir = cfg.save_dir
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
        args = self.parser.parse_args(cli_args)
        run_func = instantiate

        root_cfg = self.load_config(args)
        logger.info(f"Loaded root config: {root_cfg}")
        # Select Node
        node_cfg = root_cfg
        if args.select:
            node_cfg = OmegaConf.select(root_cfg, args.select)
            logger.debug(f"Loaded node config: {node_cfg}")

            if node_cfg is None:
                raise FlexLockValidationError(
                    f"Selection '{args.select}' returned None."
                )

        if base_cfg is not None:
            _b = base_cfg.copy()
            _b.merge_with(node_cfg)
            node_cfg.merge_with(_b) # to keep global keys pointers from root_cfg

        # Inner Overrides
        if args.merge_after_select:
            node_cfg.merge_with(OmegaConf.load(args.merge_after_select))
        if args.overrides_after_select:
            node_cfg.merge_with(OmegaConf.from_dotlist(args.overrides_after_select))

        # Print config if requested
        if args.print_config:
            print("=== COMPILED CONFIG ===")
            print(OmegaConf.to_yaml(node_cfg))

            # Print target function docstring if available
            if "_target_" in node_cfg:
                try:
                    target_path = node_cfg._target_
                    # Import the target function dynamically
                    module_name, func_name = target_path.rsplit('.', 1)
                    module = __import__(module_name, fromlist=[func_name])
                    target_func = getattr(module, func_name)

                    docstring = getattr(target_func, '__doc__', None)
                    if docstring:
                        print("\n=== TARGET FUNCTION DOCSTRING ===")
                        print(f"Target: {target_path}")
                        print(f"Docstring:\n{docstring}")
                    else:
                        print(f"\n=== TARGET FUNCTION DOCSTRING ===")
                        print(f"Target: {target_path}")
                        print("No docstring available for this function.")
                except (ImportError, AttributeError, ValueError) as e:
                    print(f"\n=== TARGET FUNCTION DOCSTRING ===")
                    print(f"Could not import target function '{node_cfg._target_}': {e}")
            else:
                print("\n=== TARGET FUNCTION DOCSTRING ===")
                print("No '_target_' specified in config, no function to document.")

        # --- SWEEP HANDLING ---
        tasks = self._load_sweep_tasks(args, root_cfg)

        # Prepare node (inject save_dir)
        node_cfg = self._prepare_node(node_cfg)

        # ACTIVATE DEBUGGING GLOBALLY
        debug = args.debug or os.environ.get("FLEXLOCK_DEBUG", "false").lower() in ("1", "true")
        if debug:
            logger.info("Debug mode enabled")
            run_func = debug_on_fail(run_func)

        # Check if run already exists
        if args.check_exists and self.check_if_exists(node_cfg):
            print("Run already exists and matches current configuration. Skipping.")
            return
        if tasks:
            if debug:
                logger.info(f"Running sweep with {len(tasks)} tasks in debug mode one job, no hpc.")
                # Batch execution
                executor = ParallelExecutor(
                    func=run_func,
                    tasks=tasks,
                    task_target=args.sweep_target,  # Use sweep_target as task_target
                    cfg=node_cfg,
                    n_jobs=1,
                )
                return executor.run()
            else:
                logger.info(f"Running sweep with {len(tasks)} tasks.")
                # Batch execution
                executor = ParallelExecutor(
                    func=run_func,
                    tasks=tasks,
                    task_target=args.sweep_target,  # Use sweep_target as task_target
                    cfg=node_cfg,
                    n_jobs=args.n_jobs,
                    slurm_config=getattr(args, 'slurm_config', None),
                    pbs_config=getattr(args, 'pbs_config', None)
                )
                return executor.run()

        # Single execution
        # Extract tracking info from the node config
        repos, data, prevs = extract_tracking_info(node_cfg)
        
        # Snapshot before run
        snapshot(node_cfg, repos=repos, data=data, prevs=prevs)
        
        # Remove _snapshot_ so it is NOT passed to the user function
        if "_snapshot_" in node_cfg:
            with open_dict(node_cfg):
                del node_cfg["_snapshot_"]
        
        return run_func(node_cfg)