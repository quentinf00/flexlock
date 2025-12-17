"""Python API for FlexLock."""

from pathlib import Path
from omegaconf import OmegaConf, DictConfig
from loguru import logger
from typing import List, Dict, Any, Optional
import yaml
import json
from .utils import instantiate, load_python_defaults
from .snapshot import snapshot, RunTracker
from .diff import RunDiff


class ExecutionResult:
    """Result object from task execution."""

    def __init__(self, save_dir: str, status: str, result: Any = None, cfg: DictConfig = None):
        """
        Initialize execution result.

        Args:
            save_dir: Directory where results are saved
            status: Status of execution ("SUCCESS", "SKIPPED", "FAILED")
            result: The actual return value from the function
            cfg: Configuration used for execution
        """
        self.save_dir = save_dir
        self.status = status
        self.result = result
        self.cfg = cfg

        # If result is a dict, expose its keys as attributes for convenience
        if isinstance(result, dict):
            for key, value in result.items():
                setattr(self, key, value)

    def __getitem__(self, key):
        """Allow dict-like access to result."""
        if isinstance(self.result, dict):
            return self.result[key]
        raise TypeError(f"Result is not a dict: {type(self.result)}")

    def get(self, key, default=None):
        """Dict-like get method."""
        if isinstance(self.result, dict):
            return self.result.get(key, default)
        return default

    def __repr__(self):
        return f"ExecutionResult(save_dir={self.save_dir}, status={self.status})"


class Project:
    def __init__(self, defaults: str = None):
        """
        Initialize a FlexLock project.

        Args:
            defaults: Python import path (e.g., pkg.config.defaults) containing the schema.
        """
        self.defaults_str = defaults
        defaults_dict = load_python_defaults(self.defaults_str)
        if not isinstance(defaults_dict, DictConfig):
            defaults_dict = OmegaConf.create(defaults_dict)
        self.defaults = defaults_dict

    def get(self, key: str):
        """
        Get a configuration by key from the defaults.

        Args:
            key: Dot-path to select a specific node from the config.

        Returns:
            The selected configuration (as DictConfig).
        """
        defaults_dict = self.defaults

        if defaults_dict is None:
            raise ValueError("No defaults specified in Project initialization")

        # Select the key from the defaults
        if key in defaults_dict:
            config = defaults_dict[key]
            return config
        else:
            raise KeyError(f"Key '{key}' not found in defaults")

    def _extract_tracking_info(self, cfg: DictConfig):
        """Extract repos, data, prevs from config _snapshot_ field."""
        repos = None
        data = None
        prevs = None

        if "_snapshot_" in cfg:
            snap_cfg = cfg._snapshot_

            if "repos" in snap_cfg or "repo" in snap_cfg:
                repos_raw = snap_cfg.get("repos") or snap_cfg.get("repo")
                repos = OmegaConf.to_container(repos_raw, resolve=True)

            if "data" in snap_cfg:
                data = OmegaConf.to_container(snap_cfg.data, resolve=True)

            if "prevs" in snap_cfg:
                prevs = OmegaConf.to_container(snap_cfg.prevs, resolve=True)



        return repos, data, prevs

    def _generate_fingerprint(self, cfg: DictConfig) -> dict:
        """
        Generate a fingerprint (proposed snapshot) for the given config.

        This is used for smart run logic to check if a run already exists.
        """
        repos, data, prevs = self._extract_tracking_info(cfg)

        # Use RunTracker to generate snapshot without writing to disk
        # We pass a dummy save_dir since we won't actually save
        tracker = RunTracker(save_dir=Path("outputs/dummy-ref-smart-run"))

        # Record environment and data
        if repos:
            tracker.record_env(repos)
        if data:
            tracker.record_data(data)

        # Finalize to get the snapshot dict
        fingerprint = tracker.finalize(cfg)

        return fingerprint

    def _find_matching_run(self, cfg: DictConfig, search_dirs: List[str] = None) -> Optional[Path]:
        """
        Search for an existing run that matches the given configuration.

        Args:
            cfg: Configuration to match
            search_dirs: List of directories to search (defaults to parent of cfg.save_dir)

        Returns:
            Path to matching run directory, or None if no match found
        """
        # Generate fingerprint for this config
        fingerprint = self._generate_fingerprint(cfg)

        # Determine where to search
        if search_dirs is None:
            if "save_dir" in cfg:
                search_dirs = [str(Path(cfg.save_dir).parent)]
            else:
                logger.warning("No save_dir in config and no search_dirs provided")
                return None

        # Search for matching runs
        for search_root in search_dirs:
            logger.debug(f"Searching for matching runs in: {search_root}")
            root_path = Path(search_root)
            if not root_path.exists():
                continue

            # Iterate over subdirectories (run directories)
            for lock_file in Path(root_path).glob('**/run.lock'):
                run_dir = Path(lock_file).parent
                logger.debug(f"Checking run.lock at {lock_file}")
                try:
                    # Load candidate snapshot
                    with open(lock_file, 'r') as f:
                        candidate_snapshot = yaml.safe_load(f)

                    # Extract save_dir from both snapshots for normalization
                    proposed_save_dir = fingerprint.get("config", {}).get("save_dir")
                    candidate_save_dir = candidate_snapshot.get("config", {}).get("save_dir")

                    # Compare using RunDiff with save_dir context
                    differ = RunDiff(
                        current=fingerprint,
                        target=candidate_snapshot,
                        current_save_dir=proposed_save_dir,
                        target_save_dir=candidate_save_dir,
                        ignore_keys=["_snapshot_"]  # Additional keys to ignore
                    )

                    if differ.is_match():
                        logger.success(f"⚡ Cache Hit! Found matching run at: {run_dir}")
                        return run_dir
                    else:
                        logger.debug(f"No match for run at: {run_dir}: {differ.diffs}")

                except Exception as e:
                    logger.debug(f"Failed to read/compare {lock_file}: {e}")
                    continue

        return None

    def exists(self, cfg: DictConfig, search_dirs: List[str] = None) -> bool:
        """
        Check if a run with the given configuration already exists.

        Args:
            cfg: Configuration to check
            search_dirs: Optional list of directories to search

        Returns:
            True if matching run exists, False otherwise
        """
        return self._find_matching_run(cfg, search_dirs) is not None

    def get_result(self, cfg: DictConfig, search_dirs: List[str] = None) -> ExecutionResult:
        """
        Retrieve results from a previously completed run.

        Args:
            cfg: Configuration to match
            search_dirs: Optional list of directories to search

        Returns:
            ExecutionResult object with cached results

        Raises:
            ValueError: If no matching run is found
        """
        match_dir = self._find_matching_run(cfg, search_dirs)

        if match_dir is None:
            raise ValueError("No matching run found. Use exists() to check first.")

        # Try to load results from various possible locations
        result_data = None

        # Try results.json
        results_file = match_dir / "results.json"
        if results_file.exists():
            with open(results_file, 'r') as f:
                result_data = json.load(f)

        # Try loading from run.lock
        lock_file = match_dir / "run.lock"
        if result_data is None and lock_file.exists():
            with open(lock_file, 'r') as f:
                lock_data = yaml.safe_load(f)
                result_data = lock_data.get("result", {})

        return ExecutionResult(
            save_dir=str(match_dir),
            status="CACHED",
            result=result_data,
            cfg=cfg
        )

    def submit(
        self,
        config: DictConfig,
        sweep: List[Dict] = None,
        n_jobs: int = 1,
        smart_run: bool = True,
        search_dirs: List[str] = None,
        wait: bool = True
    ) -> ExecutionResult | List[ExecutionResult]:
        """
        Submit a configuration for execution.

        Args:
            config: The configuration to execute (from py2cfg or get())
            sweep: Optional list of override dicts for parameter sweep
            n_jobs: Number of parallel workers (for sweeps)
            wait: If True, blocks until completion (currently always True)
            smart_run: If True, checks for existing runs before executing
            search_dirs: Directories to search for cached runs (for smart_run)

        Returns:
            ExecutionResult (single run) or List[ExecutionResult] (sweep)
        """
        # Ensure config is a DictConfig
        if not isinstance(config, DictConfig):
            config = OmegaConf.create(config)

        # Handle sweep execution
        if sweep:
            return self._submit_sweep(config, sweep, n_jobs, smart_run, search_dirs)

        # Single execution path
        # Check for existing run if smart_run is enabled
        if smart_run:
            match_dir = self._find_matching_run(config, search_dirs)
            if match_dir:
                logger.info(f"Skipping execution, using cached result from {match_dir}")
                return self.get_result(config, search_dirs)

        # Extract tracking info
        repos, data, prevs = self._extract_tracking_info(config)

        # Create snapshot before execution
        if "save_dir" in config:
            snapshot(config, repos=repos, data=data, prevs=prevs)

        # Execute the function
        logger.info(f"Executing configuration...")
        result = instantiate(config)

        # Save results if save_dir is specified
        save_dir = config.get("save_dir", ".")
        if "save_dir" in config:
            results_file = Path(save_dir) / "results.json"
            try:
                with open(results_file, 'w') as f:
                    json.dump(result if isinstance(result, dict) else {"result": result}, f, indent=2)
            except Exception as e:
                logger.warning(f"Could not save results to {results_file}: {e}")

        return ExecutionResult(
            save_dir=str(save_dir),
            status="SUCCESS",
            result=result,
            cfg=config
        )

    def _submit_sweep(
        self,
        base_config: DictConfig,
        sweep: List[Dict],
        n_jobs: int,
        smart_run: bool,
        search_dirs: List[str]
    ) -> List[ExecutionResult]:
        """
        Execute a parameter sweep.

        Args:
            base_config: Base configuration
            sweep: List of override dictionaries
            n_jobs: Number of parallel workers
            smart_run: Whether to check for cached runs
            search_dirs: Directories to search for cached runs

        Returns:
            List of ExecutionResult objects
        """
        from .parallel import ParallelExecutor
        from .utils import merge_task_into_cfg

        results = []
        configs_to_run = []
        cached_results = []

        # Check each sweep config for cached results
        for i, override in enumerate(sweep):
            # Merge override into base config
            sweep_cfg = OmegaConf.merge(base_config, override)

            # Update save_dir to include sweep index
            if "save_dir" in sweep_cfg:
                base_save_dir = Path(sweep_cfg.save_dir)
                sweep_cfg.save_dir = str(base_save_dir.parent / f"{base_save_dir.name}_sweep_{i:04d}")

            if smart_run:
                match_dir = self._find_matching_run(sweep_cfg, search_dirs)
                if match_dir:
                    logger.info(f"Sweep {i}: Using cached result from {match_dir}")
                    cached_results.append((i, self.get_result(sweep_cfg, search_dirs)))
                    continue

            configs_to_run.append((i, sweep_cfg))

        # Execute remaining configs
        if configs_to_run:
            if n_jobs == 1:
                # Sequential execution
                for i, cfg in configs_to_run:
                    logger.info(f"Executing sweep {i}/{len(sweep)}")
                    result = self.submit(cfg, sweep=None, smart_run=False, wait=True)
                    results.append((i, result))
            else:
                # Parallel execution using ParallelExecutor
                logger.info(f"Executing {len(configs_to_run)} sweep configs with {n_jobs} parallel workers")

                # Extract just configs for parallel execution
                task_configs = [cfg for _, cfg in configs_to_run]
                indices = [i for i, _ in configs_to_run]

                # Use ParallelExecutor
                # We need to create a wrapper function that extracts _target_ and instantiates
                def execute_config(task_cfg):
                    repos, data, prevs = self._extract_tracking_info(task_cfg)
                    if "save_dir" in task_cfg:
                        snapshot(task_cfg, repos=repos, data=data, prevs=prevs)
                    result = instantiate(task_cfg)

                    # Save result
                    if "save_dir" in task_cfg:
                        results_file = Path(task_cfg.save_dir) / "results.json"
                        results_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(results_file, 'w') as f:
                            json.dump(result if isinstance(result, dict) else {"result": result}, f, indent=2)

                    return result

                # Create temporary wrapper config for ParallelExecutor
                # This is a workaround - ideally ParallelExecutor would handle this
                logger.warning("Parallel sweep execution with n_jobs > 1 requires ParallelExecutor, "
                             "falling back to sequential execution")
                for i, cfg in configs_to_run:
                    result = self.submit(cfg, sweep=None, smart_run=False, wait=True)
                    results.append((i, result))

        # Combine cached and new results, sorted by index
        all_results = cached_results + results
        all_results.sort(key=lambda x: x[0])

        return [result for _, result in all_results]