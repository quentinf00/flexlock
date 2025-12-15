"""Runner for FlexLock experiments."""

import argparse
from omegaconf import OmegaConf, open_dict
from datetime import datetime
from pathlib import Path
from flexlock.utils import instantiate
from .utils import load_python_defaults
from .parallel import ParallelExecutor
from .snapshot import snapshot
from .diff import RunDiff
import yaml


class FlexLockRunner:
    def __init__(self):
        self.parser = argparse.ArgumentParser(description="FlexLock Runner")
        # Add arguments as specified in the refactor document
        self.parser.add_argument(
            "-d", "--defaults", required=True,
            help="Python import path (e.g., pkg.config.defaults) containing the schema."
        )
        self.parser.add_argument(
            "-c", "--config", 
            help="Path to a base YAML file (overrides defaults)."
        )
        self.parser.add_argument(
            "-s", "--select",
            help="Dot-path to select a specific node (experiment/stage) to run."
        )
        self.parser.add_argument(
            "--sweep-from",
            help="Key in the *root* config containing a list of task overrides (triggers ParallelExecutor)."
        )
        self.parser.add_argument(
            "-m", "--merge", 
            help="Path to a file to merge (outer override, pre-selection)."
        )
        self.parser.add_argument(
            "-o", "--overrides", nargs="*", default=[],
            help="Dotlist of overrides for outer config (pre-selection)."
        )
        self.parser.add_argument(
            "-M", "--merge-after-select",
            help="Path to a file to merge (inner override, post-selection)."
        )
        self.parser.add_argument(
            "-O", "--overrides-after-select", nargs="*", default=[],
            help="Dotlist of overrides for inner config (post-selection)."
        )
        self.parser.add_argument(
            "--n_jobs", type=int, default=1,
            help="Number of parallel workers (for sweeps)."
        )
        self.parser.add_argument(
            "--check-exists", action="store_true",
            help="Check if run already exists and skip if so."
        )

    def load_config(self, args):
        # 1. Base (Python Defaults)
        cfg = OmegaConf.create()
        if args.defaults:
            cfg = OmegaConf.create(load_python_defaults(args.defaults))

        # 2. Outer Overrides
        if args.config: 
            cfg.merge_with(OmegaConf.load(args.config))
        if args.merge: 
            cfg.merge_with(OmegaConf.load(args.merge))
        if args.overrides: 
            cfg.merge_with(OmegaConf.from_dotlist(args.overrides))

        return cfg

    def _prepare_node(self, cfg, name="exp"):
        # Inject save_dir if missing
        if "save_dir" not in cfg:
             ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
             path = Path("outputs") / name / ts
             with open_dict(cfg):
                 cfg.save_dir = str(path)
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

    def run(self, cli_args=None):
        args = self.parser.parse_args(cli_args)
        root_cfg = self.load_config(args)

        # Extract tasks if sweeping
        tasks = []
        if args.sweep_from:
             tasks = OmegaConf.select(root_cfg, args.sweep_from)

        # Select Node
        node_cfg = root_cfg
        if args.select:
            node_cfg = OmegaConf.select(root_cfg, args.select)

        # Inner Overrides
        if args.merge_after_select:
            node_cfg.merge_with(OmegaConf.load(args.merge_after_select))
        if args.overrides_after_select:
            node_cfg.merge_with(OmegaConf.from_dotlist(args.overrides_after_select))

        # Prepare node (inject save_dir)
        node_cfg = self._prepare_node(node_cfg)

        # Check if run already exists
        if args.check_exists and self.check_if_exists(node_cfg):
            print("Run already exists and matches current configuration. Skipping.")
            return

        if tasks:
            # Batch execution
            executor = ParallelExecutor(
                instantiate, 
                tasks, 
                task_to=args.sweep_from.split('.')[-1],  # Use the key part of sweep-from
                cfg=node_cfg, 
                n_jobs=args.n_jobs
            )
            return executor.run()
        else:
            # Single execution
            # Snapshot before run
            repos = {"main": "."}  # Default repo
            data_paths = {}  # Extract from config if needed
            snapshot(node_cfg, repos=repos, data=data_paths)
            return instantiate(node_cfg)