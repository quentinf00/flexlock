"""Python API for FlexLock."""

from pathlib import Path
from omegaconf import OmegaConf, DictConfig
from loguru import logger
from typing import List, Dict, Any, Optional
import yaml
import json
from .utils import instantiate, load_python_defaults, extract_tracking_info
from .snapshot import snapshot, RunTracker
from .diff import RunDiff
from . import config


class ExecutionResult:
    """Result object from task execution."""

    def __init__(
        self, save_dir: str, status: str, result: Any = None, cfg: DictConfig = None
    ):
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

    def _generate_fingerprint(self, cfg: DictConfig) -> dict:
        """
        Generate a fingerprint (proposed snapshot) for the given config.

        This is used for smart run logic to check if a run already exists.
        """
        repos, data, prevs = extract_tracking_info(cfg)

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

    def _find_matching_run(
        self,
        cfg: DictConfig,
        search_dirs: List[str] = None,
        match_include: List[str] = None,
        match_exclude: List[str] = None,
    ) -> Optional[Path]:
        """
        Search for an existing run that matches the given configuration.

        Args:
            cfg: Configuration to match
            search_dirs: List of directories to search (defaults to parent of cfg.save_dir)
            match_include: Override include patterns for git comparison
            match_exclude: Override exclude patterns for git comparison

        Returns:
            Path to matching run directory, or None if no match found
        """
        # Generate fingerprint for this config
        fingerprint = self._generate_fingerprint(cfg)

        # Determine where to search
        if search_dirs is None:
            if config.WARN_SMART_RUN_NO_SEARCH_DIRS:
                logger.warning(
                    "smart_run=True but search_dirs=None. "
                    "Defaulting to parent of save_dir. "
                    "This may not find all cached runs. "
                    "Set FLEXLOCK_WARN_SMART_RUN=0 to disable this warning."
                )
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
            for lock_file in Path(root_path).glob("**/run.lock"):
                run_dir = Path(lock_file).parent
                logger.debug(f"Checking run.lock at {lock_file}")
                try:
                    # Load candidate snapshot
                    with open(lock_file, "r") as f:
                        candidate_snapshot = yaml.safe_load(f)

                    # Extract save_dir from both snapshots for normalization
                    proposed_save_dir = fingerprint.get("config", {}).get("save_dir")
                    candidate_save_dir = candidate_snapshot.get("config", {}).get(
                        "save_dir"
                    )

                    # Compare using RunDiff with save_dir context
                    differ = RunDiff(
                        current=fingerprint,
                        target=candidate_snapshot,
                        current_save_dir=proposed_save_dir,
                        target_save_dir=candidate_save_dir,
                        ignore_keys=["_snapshot_"],
                        match_include=match_include,
                        match_exclude=match_exclude,
                    )

                    if differ.is_match():
                        logger.success(
                            f"⚡ Cache Hit! Found matching run at: {run_dir}"
                        )
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

    def get_result(
        self, cfg: DictConfig, search_dirs: List[str] = None
    ) -> ExecutionResult:
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
            with open(results_file, "r") as f:
                result_data = json.load(f)

        # Try loading from run.lock
        lock_file = match_dir / "run.lock"
        if result_data is None and lock_file.exists():
            with open(lock_file, "r") as f:
                lock_data = yaml.safe_load(f)
                result_data = lock_data.get("result", {})

        return ExecutionResult(
            save_dir=str(match_dir), status="CACHED", result=result_data, cfg=cfg
        )

    def submit(
        self,
        config: DictConfig,
        sweep: List[Dict] = None,
        n_jobs: int = 1,
        smart_run: bool = True,
        search_dirs: List[str] = None,
        wait: bool = True,
        pbs_config: str = None,
        slurm_config: str = None,
        sweep_dir_suffix: bool = False,
        match_include: List[str] = None,
        match_exclude: List[str] = None,
    ) -> ExecutionResult | List[ExecutionResult]:
        """
        Submit a configuration for execution.

        Args:
            config: The configuration to execute (from py2cfg or get())
            sweep: Optional list of override dicts for parameter sweep
            n_jobs: Number of parallel workers (for sweeps)
            wait: If True, blocks until completion
            smart_run: If True, checks for existing runs before executing
            search_dirs: Directories to search for cached runs (for smart_run)
            pbs_config: Path to PBS configuration YAML (for HPC execution)
            slurm_config: Path to Slurm configuration YAML (for HPC execution)
            match_include: Override include patterns for git comparison during smart_run
            match_exclude: Override exclude patterns for git comparison during smart_run

        Returns:
            ExecutionResult (single run) or List[ExecutionResult] (sweep)

        Notes:
            - Use pbs_config or slurm_config for HPC backend execution
            - For Singularity containers, specify python_exe in the backend config
            - wait=True will poll job status until completion (for HPC backends)
        """
        # Ensure config is a DictConfig
        if not isinstance(config, DictConfig):
            config = OmegaConf.create(config)

        # Handle sweep execution
        if sweep:
            return self._submit_sweep(
                config,
                sweep,
                n_jobs,
                smart_run,
                search_dirs,
                pbs_config,
                slurm_config,
                wait,
                sweep_dir_suffix,
                match_include,
                match_exclude,
            )

        # Single execution path
        # Check for existing run if smart_run is enabled
        if smart_run:
            match_dir = self._find_matching_run(
                config, search_dirs, match_include, match_exclude
            )
            if match_dir:
                logger.info(f"Skipping execution, using cached result from {match_dir}")
                return self.get_result(config, search_dirs)

        # Check if using HPC backend
        use_hpc = pbs_config is not None or slurm_config is not None

        if use_hpc:
            # Execute via HPC backend
            logger.info(f"Submitting to HPC backend...")

            # Use ParallelExecutor with a single task
            from .parallel import ParallelExecutor

            save_dir = config.get("save_dir", "outputs/job")
            executor_cfg = OmegaConf.create(
                {"save_dir": str(save_dir), "_snapshot_": config.get("_snapshot_", {})}
            )

            executor = ParallelExecutor(
                func=instantiate,
                tasks=[config],  # Single task as a list
                task_target=None,
                cfg=executor_cfg,
                n_jobs=config.DEFAULT_N_JOBS,
                pbs_config=pbs_config,
                slurm_config=slurm_config,
                local_workers=None,
            )

            # Run with wait parameter (executor handles waiting)
            success = executor.run(
                wait=wait, timeout=config.DEFAULT_TIMEOUT if wait else None
            )

            # Load result
            result_data = None
            if "save_dir" in config:
                results_file = Path(config.save_dir) / "results.json"
                if results_file.exists():
                    with open(results_file, "r") as f:
                        result_data = json.load(f)

            return ExecutionResult(
                save_dir=str(save_dir),
                status="SUCCESS" if wait else "SUBMITTED",
                result=result_data,
                cfg=config,
            )

        else:
            # Local execution
            # Extract tracking info
            repos, data, prevs = extract_tracking_info(config)

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
                    with open(results_file, "w") as f:
                        json.dump(
                            result if isinstance(result, dict) else {"result": result},
                            f,
                            indent=2,
                        )
                except Exception as e:
                    logger.warning(f"Could not save results to {results_file}: {e}")

            return ExecutionResult(
                save_dir=str(save_dir), status="SUCCESS", result=result, cfg=config
            )

    def _submit_sweep(
        self,
        base_config: DictConfig,
        sweep: List[Dict],
        n_jobs: int,
        smart_run: bool,
        search_dirs: List[str],
        pbs_config: str = None,
        slurm_config: str = None,
        wait: bool = True,
        dir_suffix: bool = False,
        match_include: List[str] = None,
        match_exclude: List[str] = None,
    ) -> List[ExecutionResult]:
        """
        Execute a parameter sweep.

        Args:
            base_config: Base configuration
            sweep: List of override dictionaries
            n_jobs: Number of parallel workers
            smart_run: Whether to check for cached runs
            search_dirs: Directories to search for cached runs
            pbs_config: Path to PBS configuration YAML
            slurm_config: Path to Slurm configuration YAML
            wait: Whether to wait for jobs to complete
            match_include: Override include patterns for git comparison
            match_exclude: Override exclude patterns for git comparison

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
            sweep_cfg = OmegaConf.merge(base_config, override)

            # This makes the config self-contained for DB serialization.
            sweep_cfg = OmegaConf.create(
                OmegaConf.to_container(sweep_cfg, resolve=True)
            )

            # Update save_dir to include sweep index
            if dir_suffix and "save_dir" in sweep_cfg:
                base_save_dir = Path(sweep_cfg.save_dir)
                sweep_cfg.save_dir = str(
                    base_save_dir.parent / f"{base_save_dir.name}_sweep_{i:04d}"
                )

            if smart_run:
                match_dir = self._find_matching_run(
                    sweep_cfg, search_dirs, match_include, match_exclude
                )
                if match_dir:
                    logger.info(f"Sweep {i}: Using cached result from {match_dir}")
                    cached_results.append((i, self.get_result(sweep_cfg, search_dirs)))
                    continue

            configs_to_run.append((i, sweep_cfg))

        # Execute remaining configs
        if configs_to_run:
            # Decide whether to use HPC backend or local execution
            use_hpc = pbs_config is not None or slurm_config is not None

            if use_hpc or (n_jobs > 1 and len(configs_to_run) > 1):
                # Parallel execution using ParallelExecutor (local or HPC)
                logger.info(
                    f"Executing {len(configs_to_run)} sweep configs with ParallelExecutor"
                )

                # Extract just configs for parallel execution
                task_configs = [cfg for _, cfg in configs_to_run]
                indices = [i for i, _ in configs_to_run]

                # Prepare a common save_dir for the sweep master
                # Use the first config's save_dir as base
                if "save_dir" in task_configs[0]:
                    sweep_save_dir = Path(task_configs[0].save_dir).parent
                else:
                    sweep_save_dir = Path("outputs/sweep")

                # Create a wrapper config that ParallelExecutor can work with
                # The task configs are what ParallelExecutor will execute
                # Resolve _snapshot_ while base_config still has its parent chain
                # so that OmegaConf interpolations (e.g. ${...key}) can resolve
                if "_snapshot_" in base_config:
                    snapshot_resolved = OmegaConf.to_container(
                        base_config._snapshot_, resolve=True
                    )
                else:
                    snapshot_resolved = {}

                executor_cfg = OmegaConf.create(
                    {
                        "save_dir": str(sweep_save_dir),
                        "_snapshot_": snapshot_resolved,
                    }
                )

                # Use ParallelExecutor with backend support
                executor = ParallelExecutor(
                    func=instantiate,  # The function to execute
                    tasks=task_configs,  # List of configs to execute
                    task_target=None,  # Each task is already a complete config
                    cfg=executor_cfg,  # Master config for tracking
                    n_jobs=n_jobs,
                    pbs_config=pbs_config,
                    slurm_config=slurm_config,
                    local_workers=n_jobs if not use_hpc else None,
                )

                # Run the sweep (executor handles waiting based on wait parameter)
                success = executor.run(wait=wait, timeout=None)

                # Collect results from executed configs
                for idx, cfg in zip(indices, task_configs):
                    # Try to load results
                    result_data = None
                    if "save_dir" in cfg:
                        results_file = Path(cfg.save_dir) / "results.json"
                        if results_file.exists():
                            with open(results_file, "r") as f:
                                result_data = json.load(f)

                    results.append(
                        (
                            idx,
                            ExecutionResult(
                                save_dir=str(cfg.get("save_dir", ".")),
                                status="SUCCESS",
                                result=result_data,
                                cfg=cfg,
                            ),
                        )
                    )
            else:
                # Sequential execution (no backend, n_jobs=1)
                for i, cfg in configs_to_run:
                    logger.info(f"Executing sweep {i}/{len(sweep)}")
                    result = self.submit(cfg, sweep=None, smart_run=False, wait=True)
                    results.append((i, result))

        # Combine cached and new results, sorted by index
        all_results = cached_results + results
        all_results.sort(key=lambda x: x[0])

        return [result for _, result in all_results]
