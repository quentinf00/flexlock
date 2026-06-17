"""Python API for FlexLock."""

from pathlib import Path
from omegaconf import OmegaConf, DictConfig, open_dict
from loguru import logger
from typing import List, Dict, Any, Optional
import yaml
import json
from .utils import (
    instantiate,
    load_python_defaults,
    extract_tracking_info,
    select_and_freeze_root_refs,
)
from .snapshot import snapshot, RunTracker, write_complete_marker
from .diff import RunDiff
from . import config as flexlock_config


def _print_compiled_config(cfg):
    """Print the resolved config + the target function's docstring, matching
    what the docs promise for ``--print-config`` / ``print_config=True``.
    """
    print("=== COMPILED CONFIG ===")
    print(OmegaConf.to_yaml(cfg))
    target = cfg.get("_target_") if isinstance(cfg, DictConfig) else None
    if not target:
        return
    print("=== TARGET FUNCTION DOCSTRING ===")
    print(f"Target: {target}")
    try:
        import importlib

        module_name, func_name = target.rsplit(".", 1)
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        doc = getattr(func, "__doc__", None)
        print(f"Docstring:\n{doc}" if doc else "No docstring available.")
    except (ImportError, AttributeError, ValueError) as e:
        print(f"Could not import target function '{target}': {e}")


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


class ChainedResult:
    """Return type for :meth:`Project.submit_chained`.

    Attributes:
        sweep: List of sweep ``ExecutionResult`` objects.
        downstream: List of lists; ``downstream[i][j]`` is the result of
            the ``j``-th downstream stage for the ``i``-th sweep item.
    """

    def __init__(
        self,
        sweep: List[ExecutionResult],
        downstream: List[List[ExecutionResult]],
    ):
        self.sweep = sweep
        self.downstream = downstream

    def __iter__(self):
        """Iterate (sweep_result, downstream_results) pairs."""
        return iter(zip(self.sweep, self.downstream))

    def __len__(self):
        return len(self.sweep)

    def __repr__(self):
        n_down = len(self.downstream[0]) if self.downstream else 0
        return (
            f"ChainedResult(sweep={len(self.sweep)}, "
            f"downstream_per_item={n_down})"
        )


class Project:
    def __init__(self, defaults: "str | DictConfig | dict | None" = None):
        """Initialize a FlexLock project.

        Args:
            defaults: One of:
                - Python import path string (``'pkg.config.defaults'`` or
                  ``'path/to/file.py:defaults'``)
                - A pre-built ``DictConfig`` or plain dict
                - ``None`` for a project with no defaults — useful for
                  one-off submissions of an explicit config.
        """
        if defaults is None:
            self.defaults_str = None
            self.defaults = OmegaConf.create({})
        elif isinstance(defaults, str):
            self.defaults_str = defaults
            loaded = load_python_defaults(defaults)
            self.defaults = (
                loaded if isinstance(loaded, DictConfig) else OmegaConf.create(loaded)
            )
        else:
            self.defaults_str = None
            self.defaults = (
                defaults
                if isinstance(defaults, DictConfig)
                else OmegaConf.create(defaults)
            )

    def get(self, key: str):
        """
        Get a configuration by key from the defaults.

        The returned config is self-contained: root-scope ``${...}`` references
        are frozen into concrete values, while resolver calls (``${vinc:}``,
        ``${latest:}``, ``${run_lock:}``, etc.) and intra-sub-tree refs are
        preserved for resolution at submit time. This means the returned
        config can be pickled, modified, and submitted without losing root
        context (essential for HPC submission).

        Args:
            key: Dot-path to select a specific node from the defaults.

        Returns:
            The selected configuration (as DictConfig).
        """
        if self.defaults is None:
            raise ValueError("No defaults specified in Project initialization")
        return select_and_freeze_root_refs(self.defaults, key)

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
        # Auto-populate match_include from _target_ modules if not provided
        if match_include is None:
            from .utils import collect_target_include_patterns

            match_include = collect_target_include_patterns(cfg) or None

        # Generate fingerprint for this config
        fingerprint = self._generate_fingerprint(cfg)

        # Determine where to search
        if search_dirs is None:
            if flexlock_config.WARN_SMART_RUN_NO_SEARCH_DIRS:
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
                        # Require run.complete — interrupted runs left only
                        # run.lock and must not be treated as cache hits.
                        if not (run_dir / "run.complete").exists():
                            logger.debug(
                                f"Match at {run_dir} has no run.complete "
                                f"(previous attempt incomplete); skipping"
                            )
                            continue

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

    def run_stage(
        self, cfg, stage_name=None, smart_run=True, search_dirs=None, **submit_kwargs
    ):
        """
        Run a single stage with automatic search_dirs and save_dir propagation.

        Args:
            cfg: Stage configuration (DictConfig)
            stage_name: Name of the stage (inferred from save_dir if None)
            smart_run: If True, checks for cached runs
            search_dirs: Directories to search for cached runs (auto-discovered if None)
            **submit_kwargs: Additional arguments passed to submit()

        Returns:
            ExecutionResult (or list for sweeps)
        """
        # Infer stage name from save_dir
        if stage_name is None and "save_dir" in cfg:
            stage_name = Path(cfg.save_dir).name

        # Auto-discover search_dirs: look for sibling experiment dirs with same stage name
        if search_dirs is None and smart_run and stage_name and "save_dir" in cfg:
            parent = Path(cfg.save_dir).parent.parent
            if parent.exists():
                search_dirs = [
                    str(p) for p in parent.glob(f"*/{stage_name}") if p.is_dir()
                ]

        result = self.submit(
            cfg, smart_run=smart_run, search_dirs=search_dirs, **submit_kwargs
        )

        # For single runs, propagate save_dir back into cfg
        if isinstance(result, list):
            return result
        with open_dict(cfg):
            cfg.save_dir = result.save_dir
        return result

    def save_snapshot(self, save_dir):
        """
        Save the current project defaults as pipeline.yaml.

        Args:
            save_dir: Directory to save the pipeline snapshot to
        """
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        (save_path / "pipeline.yaml").write_text(OmegaConf.to_yaml(self.defaults))

    def submit(
        self,
        config: "DictConfig | str | None" = None,
        sweep: List[Dict] = None,
        sweep_target: str = None,
        sweep_root: "str | None" = None,
        n_jobs: int = 1,
        smart_run: bool = True,
        search_dirs: List[str] = None,
        wait: bool = True,
        pbs_config: str = None,
        slurm_config: str = None,
        sweep_dir_suffix: bool = False,
        match_include: List[str] = None,
        match_exclude: List[str] = None,
        isolated: bool = False,
        force: bool = False,
        overrides: "dict | List[str] | None" = None,
        merge: "str | Path | dict | None" = None,
        debug: bool = False,
        print_config: bool = False,
        dry_run: bool = False,
    ) -> "ExecutionResult | List[ExecutionResult] | None":
        """Submit a configuration for execution.

        Args:
            config: The configuration to execute. Accepts a ``DictConfig``,
                a key string (looked up via :meth:`get`), or ``None`` (uses
                ``self.defaults`` as-is).
            sweep: Optional list of override dicts for parameter sweep.
            sweep_target: Dot-path inside each task config where the sweep
                item is merged. When ``None``, items merge at the root of
                ``config``.
            n_jobs: Number of parallel workers (for sweeps).
            smart_run: If True, checks for an existing cached run before
                executing.
            search_dirs: Directories to search for cached runs.
            wait: If True, blocks until completion.
            pbs_config / slurm_config: Path to HPC backend YAML.
            sweep_dir_suffix: If True, append ``_sweep_{i:04d}`` to each
                sweep item's ``save_dir``.
            match_include / match_exclude: Override git path patterns used
                during ``smart_run`` comparison.
            isolated: If True, run in a spawned subprocess even for a
                single task (use for GPU stages to confine the CUDA
                context).
            force: If True, invalidate the cache marker (``run.complete``)
                for this ``save_dir`` and re-execute. Outputs and
                ``run.lock`` are preserved; the user function overwrites
                in place.
            overrides: Dict (``{'lr': 0.01}``) or dotlist
                (``['lr=0.01']``) merged into ``config`` before execution.
            merge: Path to a YAML file (or a dict) merged into ``config``
                before execution. ``overrides`` is applied after ``merge``.
            debug: Wrap the user function with the post-mortem debugger so
                exceptions drop into PDB.
            print_config: Print the fully-resolved config and return
                ``None`` without executing.
            dry_run: When using an HPC backend, render the would-be Slurm
                or PBS submission script, print it (with any validation
                warnings), and return ``None`` without submitting. No-op
                for local execution.

        Returns:
            ``ExecutionResult`` (single), ``List[ExecutionResult]`` (sweep),
            or ``None`` (``print_config=True``).
        """
        # Resolve config from a key, a DictConfig, or default to self.defaults.
        if config is None:
            config = self.defaults
        elif isinstance(config, str):
            config = self.get(config)
        if not isinstance(config, DictConfig):
            config = OmegaConf.create(config)

        # Apply post-resolution merges and overrides (post-select equivalents).
        if merge is not None:
            if isinstance(merge, (str, Path)):
                config.merge_with(OmegaConf.load(str(merge)))
            else:
                config.merge_with(OmegaConf.create(merge))
        if overrides is not None:
            if isinstance(overrides, dict):
                overrides = [f"{k}={v}" for k, v in overrides.items()]
            config.merge_with(OmegaConf.from_dotlist(overrides))

        # Resolve save_dir exactly once. Resolvers like ${vinc:} look at the
        # filesystem and would otherwise advance the counter every time
        # cfg.save_dir is read (snapshot phase vs. complete-marker phase),
        # splitting run.lock and run.complete across different dirs.
        if "save_dir" in config:
            try:
                if config.save_dir is not None:
                    with open_dict(config):
                        config.save_dir = str(config.save_dir)
            except Exception:
                # save_dir contains an interpolation that can't resolve in this
                # config's scope (e.g. a sub-config passed in isolation with
                # save_dir: ${save_dir}/features). Leave it unresolved.
                pass

        if print_config:
            # When a sweep is given, preview each item's merged config so
            # the user can verify per-item interpolations resolve correctly
            # before launching.
            if sweep:
                from .utils import merge_task_into_cfg

                for i, override in enumerate(sweep):
                    item_cfg = merge_task_into_cfg(config, override, sweep_target)
                    print(f"# --- sweep item {i} ---")
                    _print_compiled_config(item_cfg)
            else:
                _print_compiled_config(config)
            return None

        if force:
            # Invalidate the cache for this save_dir without touching outputs.
            save_dir = Path(config.get("save_dir", "outputs/job"))
            marker = save_dir / "run.complete"
            if marker.exists():
                logger.info(f"Force flag enabled: invalidating cache at {save_dir}")
                marker.unlink()
            smart_run = False

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
                sweep_target=sweep_target,
                sweep_root=sweep_root,
                debug=debug,
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

        if dry_run:
            if not use_hpc:
                logger.info("dry_run is a no-op for local execution.")
                return None
            self._preview_hpc_script(config, slurm_config, pbs_config)
            return None

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
                n_jobs=flexlock_config.DEFAULT_N_JOBS,
                pbs_config=pbs_config,
                slurm_config=slurm_config,
                local_workers=None,
            )

            # Run with wait parameter (executor handles waiting)
            success = executor.run(
                wait=wait, timeout=flexlock_config.DEFAULT_TIMEOUT if wait else None
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
            if isolated:
                # Run in an isolated spawned subprocess so that any GPU/CUDA
                # context initialised inside the task stays in the child and
                # never leaks into the parent (which may later fork workers).
                from .parallel import ParallelExecutor

                save_dir = config.get("save_dir", "outputs/job")
                if "_snapshot_" in config:
                    snapshot_resolved = OmegaConf.to_container(
                        config._snapshot_, resolve=True
                    )
                else:
                    snapshot_resolved = {}
                executor_cfg = OmegaConf.create(
                    {"save_dir": str(save_dir), "_snapshot_": snapshot_resolved}
                )
                executor = ParallelExecutor(
                    func=instantiate,
                    tasks=[config],
                    task_target=None,
                    cfg=executor_cfg,
                    n_jobs=1,
                    isolated=True,
                )
                executor.run(wait=True)
                result_data = None
                if "save_dir" in config:
                    results_file = Path(save_dir) / "results.json"
                    if results_file.exists():
                        with open(results_file, "r") as f:
                            result_data = json.load(f)
                return ExecutionResult(
                    save_dir=str(save_dir),
                    status="SUCCESS",
                    result=result_data,
                    cfg=config,
                )

            # Extract tracking info
            repos, data, prevs = extract_tracking_info(config)

            # Eagerly freeze all resolver interpolations in one pass.
            #
            # select_and_freeze_root_refs preserves ${vinc:} resolver calls
            # verbatim when freezing cross-tree refs (e.g. ${main.save_dir}
            # pointing to ${vinc:results/exp} becomes a new ${vinc:} node).
            # The save_dir freeze above already fired vinc: and cached the result
            # in this OmegaConf instance.  A full to_container(resolve=True) drains
            # that cache for every other ${vinc:} occurrence so they all get the same
            # value.  Re-wrapping as a plain config prevents instantiate()'s internal
            # config.copy() — which creates a new instance with an empty cache — from
            # firing the resolver again after snapshot() has created save_dir on disk.
            try:
                _c = OmegaConf.to_container(config, resolve=True, throw_on_missing=False)
                config = OmegaConf.create(_c)
            except Exception as exc:
                logger.warning(f"Could not fully resolve config before execution: {exc}")

            # Create snapshot before execution
            if "save_dir" in config:
                snapshot(config, repos=repos, data=data, prevs=prevs)

            # Execute the function
            logger.info(f"Executing configuration...")
            run_func = instantiate
            if debug:
                from .debug import debug_on_fail

                run_func = debug_on_fail(run_func)
            result = run_func(config)

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
                write_complete_marker(Path(save_dir), result=result)

            return ExecutionResult(
                save_dir=str(save_dir), status="SUCCESS", result=result, cfg=config
            )

    @staticmethod
    def _preview_hpc_script(config, slurm_config, pbs_config):
        """Render the would-be HPC submission script and print it.

        Used by ``submit(..., dry_run=True)``. Loads the backend YAML the
        same way :class:`ParallelExecutor` would, instantiates the backend
        targeting a temporary folder, and prints the rendered script plus
        any validation warnings.
        """
        import tempfile

        save_dir = Path(config.get("save_dir", "outputs/job"))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            if slurm_config:
                from .backends.slurm import SlurmBackend, validate_slurm_script

                params = OmegaConf.to_container(
                    OmegaConf.load(slurm_config), resolve=True
                )
                # Match ParallelExecutor's folder convention so paths in
                # the preview look like the real submission.
                params_folder = save_dir / "slurm_logs"
                backend = SlurmBackend(folder=folder, **params)
                script = backend.render_script()
                # Rewrite the temp folder path to the would-be real one so
                # the preview is faithful.
                script = script.replace(str(folder), str(params_folder))

                print("# === Slurm submission script (dry run) ===")
                print(script)
                print("# === end ===")
                warnings = validate_slurm_script(script)
                if warnings:
                    print("\n# Warnings:")
                    for w in warnings:
                        print(f"#   - {w}")
            elif pbs_config:
                from .backends.pbs import PBSBackend

                params = OmegaConf.to_container(
                    OmegaConf.load(pbs_config), resolve=True
                )
                backend = PBSBackend(folder=folder, **params)
                # PBS backend may or may not expose render_script — fall
                # back to printing the YAML if not.
                if hasattr(backend, "render_script"):
                    print("# === PBS submission script (dry run) ===")
                    print(backend.render_script())
                    print("# === end ===")
                else:
                    print("# === PBS config (dry run) ===")
                    print(OmegaConf.to_yaml(OmegaConf.create(params)))
                    print("# === end ===")

    @staticmethod
    def _validate_sweep_save_dirs(base_config, merged_items, sweep_root=None):
        """Ensure every sweep item's save_dir nests under the sweep root.

        The sweep root is taken from ``sweep_root`` when provided, then from
        ``base_config.save_dir``, otherwise from the parent of the first item's
        save_dir. The tasks DB and per-item lineage markers all assume
        containment; violating it produces an opaque crash in the worker.
        """
        from .exceptions import FlexLockValidationError

        if not merged_items:
            return

        # When the user explicitly provides a sweep_root they've opted out of
        # the containment constraint — trust them and skip validation.
        if sweep_root is not None:
            return

        # Determine sweep root.
        if "save_dir" in base_config and base_config.save_dir is not None:
            effective_root = Path(base_config.save_dir).resolve()
        else:
            first_save = merged_items[0][1].get("save_dir")
            if first_save is None:
                return  # nothing to validate against
            effective_root = Path(first_save).resolve().parent

        offenders = []
        for i, sweep_cfg in merged_items:
            sd = sweep_cfg.get("save_dir")
            if sd is None:
                continue
            try:
                Path(sd).resolve().relative_to(effective_root)
            except ValueError:
                offenders.append((i, sd))

        if offenders:
            lines = [
                f"  item {i}: save_dir={sd!r}" for i, sd in offenders
            ]
            raise FlexLockValidationError(
                f"Sweep item save_dir(s) must nest under the sweep root "
                f"({effective_root}); the tasks DB and lineage markers live "
                f"there. Offending items:\n"
                + "\n".join(lines)
                + f"\n\nTo keep the current save_dirs, use --sweep-root "
                f"<common_parent> (e.g. --sweep-root {Path(offenders[0][1]).parent})."
            )

    def submit_chained(
        self,
        config=None,
        *,
        sweep: "List[Dict] | None" = None,
        downstream: "List[tuple] | None" = None,
        sweep_kwargs: "dict | None" = None,
        downstream_kwargs: "dict | None" = None,
    ) -> "ChainedResult":
        """Run a sweep, then chain a sequence of downstream stages per result.

        For each item in ``sweep``, this method submits the base config and
        then, for each ``(stage_key, anchor_wiring)`` in ``downstream``,
        propagates the sweep result's attributes into ``proj.defaults`` and
        submits the downstream stage.

        ``anchor_wiring`` maps an anchor name in ``proj.defaults`` to an
        attribute of the parent ``ExecutionResult`` (typically
        ``'save_dir'``).

        Args:
            config: Base config for the sweep (passed to :meth:`submit`).
            sweep: List of override dicts for the parameter sweep.
            downstream: List of ``(stage_key, anchor_wiring)`` tuples
                describing the stages to run per sweep result.
            sweep_kwargs: Extra kwargs forwarded to ``submit`` for the
                sweep itself (e.g. ``slurm_config``, ``smart_run``).
            downstream_kwargs: Extra kwargs forwarded to ``submit`` for
                every downstream stage. Defaults to ``smart_run=False`` to
                avoid stale-cache false hits between iterations.

        Returns:
            ``ChainedResult`` with ``sweep`` (list) and ``downstream`` (a
            list of lists, one per sweep item, each inner list aligned to
            the order of ``downstream``).
        """
        if sweep is None or downstream is None:
            raise ValueError(
                "submit_chained requires both `sweep` and `downstream` lists. "
                "Use submit() if you don't need post-sweep chaining."
            )

        sweep_kwargs = dict(sweep_kwargs or {})
        downstream_kwargs = {"smart_run": False, **(downstream_kwargs or {})}

        sweep_results = self.submit(config, sweep=sweep, **sweep_kwargs)
        if not isinstance(sweep_results, list):
            sweep_results = [sweep_results]

        downstream_results: list[list[ExecutionResult]] = []
        for parent in sweep_results:
            per_parent: list[ExecutionResult] = []
            for entry in downstream:
                stage_key, anchor_wiring = entry
                for anchor_name, attr in anchor_wiring.items():
                    value = getattr(parent, attr, None)
                    if value is None:
                        logger.warning(
                            f"submit_chained: parent result has no '{attr}' "
                            f"attribute; anchor '{anchor_name}' not updated."
                        )
                        continue
                    OmegaConf.update(self.defaults, anchor_name, value)
                result = self.submit(stage_key, **downstream_kwargs)
                per_parent.append(result)
            downstream_results.append(per_parent)

        return ChainedResult(sweep=sweep_results, downstream=downstream_results)

    @classmethod
    def submit_config(cls, config=None, **kwargs):
        """Shortcut for one-off submissions without holding a Project instance.

        Equivalent to ``Project().submit(config, **kwargs)``. Use this when
        you already have a ``DictConfig`` (from ``py2cfg`` or otherwise) and
        don't need ``proj.get``/``proj.exists``/``proj.defaults`` plumbing.

        See :func:`flexlock.submit` for the module-level alias.
        """
        return cls().submit(config, **kwargs)

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
        sweep_target: str = None,
        sweep_root: "str | None" = None,
        debug: bool = False,
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

        # Build sweep configs first so we can validate save_dir containment
        # in one place, before any execution.
        merged_items = []
        for i, override in enumerate(sweep):
            sweep_cfg = merge_task_into_cfg(base_config, override, sweep_target)
            # Make self-contained for DB serialization.
            sweep_cfg = OmegaConf.create(
                OmegaConf.to_container(sweep_cfg, resolve=True)
            )
            if dir_suffix and "save_dir" in sweep_cfg:
                # Nest each item under the base save_dir (the sweep root) so
                # tasks DB and lineage markers stay inside the same tree.
                # Pre-fix this produced siblings (e.g. train_sweep_0000 next
                # to train/), which always tripped the containment check.
                base_save_dir = Path(sweep_cfg.save_dir)
                sweep_cfg.save_dir = str(base_save_dir / f"sweep_{i:04d}")
            merged_items.append((i, sweep_cfg))

        # Validate per-item save_dir containment up front. The tasks DB lives
        # at <sweep_root>/run.lock.tasks.db and each task records its path
        # relative to its parent dir. If items sit outside the sweep tree the
        # worker either fails opaquely (pre-validation) or can't form a
        # relative path. Surface a clear error before we queue anything.
        self._validate_sweep_save_dirs(base_config, merged_items, sweep_root=sweep_root)

        # Check each sweep config for cached results
        for i, sweep_cfg in merged_items:
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

                # Prepare a common save_dir for the sweep master (tasks DB lives here).
                if sweep_root is not None:
                    sweep_save_dir = Path(sweep_root)
                elif "save_dir" in task_configs[0]:
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
                    result = self.submit(
                        cfg, sweep=None, smart_run=False, wait=True, debug=debug
                    )
                    results.append((i, result))

        # Combine cached and new results, sorted by index
        all_results = cached_results + results
        all_results.sort(key=lambda x: x[0])

        return [result for _, result in all_results]
