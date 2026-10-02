"""Python API for FlexLock."""

from enum import Enum
from pathlib import Path
from omegaconf import OmegaConf, DictConfig, open_dict
from loguru import logger
from typing import List, Dict, Any, Optional
import yaml
import json
from .utils import (
    apply_overrides,
    defaults_module,
    expand_swaps,
    instantiate,
    load_python_defaults,
    extract_tracking_info,
    select_and_freeze_root_refs,
)
from .freeze import freeze_deferred
from .presets import freeze_run_refs
from .snapshot import snapshot, RunTracker, record_code_drift
from .run_record import RunRecord
from .fingerprint import fingerprint as compute_fingerprint
from . import index
from .diff import RunDiff
from . import config as flexlock_config
from .exceptions import FlexLockExecutionError


def _leaf_paths(container, prefix=""):
    """Yield ``(dotpath, value)`` for every leaf in a plain dict/list container.

    Dotpaths use OmegaConf's ``a.b.0`` selector form so they can be fed back to
    ``OmegaConf.select`` — used by :meth:`Project.check` to probe each leaf.
    """
    if isinstance(container, dict):
        for k, v in container.items():
            yield from _leaf_paths(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(container, list):
        for i, v in enumerate(container):
            yield from _leaf_paths(v, f"{prefix}.{i}" if prefix else str(i))
    else:
        yield prefix, container


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


class Status(str, Enum):
    """Terminal state of a run. A ``str`` subclass so ``status == "SUCCESS"``
    and f-string formatting keep working for existing callers."""

    SUCCESS = "SUCCESS"
    CACHED = "CACHED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    SUBMITTED = "SUBMITTED"
    SKIPPED = "SKIPPED"

    def __str__(self) -> str:
        return self.value


def _coerce_status(s):
    if isinstance(s, Status):
        return s
    try:
        return Status(s)
    except ValueError:
        return s  # tolerate unknown strings rather than raising


# Real attributes that a result-dict key must never shadow (issue 6).
_RESERVED_RESULT_KEYS = frozenset(
    {"save_dir", "status", "result", "metrics", "cfg", "error", "get",
     "raise_on_failure", "is_success"}
)


class ExecutionResult:
    """Typed result object from a run.

    The function's return payload is kept in ``result`` (alias ``metrics``);
    its keys are still reachable as attributes (``res.accuracy``) via
    ``__getattr__`` — but only when they don't collide with a real attribute,
    so a payload key named ``status``/``get`` no longer clobbers the object's
    own API (issue 6).
    """

    def __init__(
        self,
        save_dir: str,
        status: "str | Status",
        result: Any = None,
        cfg: DictConfig = None,
        error: "str | None" = None,
    ):
        """
        Args:
            save_dir: Directory where results are saved
            status: One of the :class:`Status` values
            result: The actual return value from the function
            cfg: Configuration used for execution
            error: Error/traceback string for FAILED items (else None)
        """
        self.save_dir = save_dir
        self.status = _coerce_status(status)
        self.result = result
        self.cfg = cfg
        self.error = error

    @property
    def metrics(self):
        """The return payload (alias for ``result``)."""
        return self.result

    @property
    def is_success(self) -> bool:
        return self.status in (Status.SUCCESS, Status.CACHED)

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

    def __getattr__(self, name):
        """Expose result-dict keys as attributes without clobbering real ones.

        Only invoked when normal attribute lookup fails, so real attributes
        (status, save_dir, ...) always win over same-named payload keys.
        """
        if name.startswith("__") or name in _RESERVED_RESULT_KEYS:
            raise AttributeError(name)
        result = self.__dict__.get("result")
        if isinstance(result, dict) and name in result:
            return result[name]
        raise AttributeError(name)

    def raise_on_failure(self) -> "ExecutionResult":
        """Raise if the run did not succeed; return self otherwise (chainable)."""
        if self.status in (Status.FAILED, Status.INTERRUPTED):
            raise FlexLockExecutionError(
                f"Run at {self.save_dir} ended {self.status}: {self.error}"
            )
        return self

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


def _reset_task_db(db_dir: Path) -> None:
    """Delete ``run.lock.tasks.db`` (+ WAL/SHM) under ``db_dir`` for a forced rerun."""
    from .taskdb import reset_db

    reset_db(Path(db_dir) / "run.lock.tasks.db")


class Project:
    # Module that bare ``@name`` overrides / sweep values resolve against
    # (set from an import-string ``defaults``; the CLI sets it from ``-d``).
    override_module = None

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
        self.override_module = (
            defaults_module(defaults) if isinstance(defaults, str) else None
        )
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
        node = select_and_freeze_root_refs(self.defaults, key)
        if self.defaults_str is not None:
            from .presets import attach, make_preset

            attach(node, make_preset(self.defaults_str, key))
        return node

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

        # Compute the pure fingerprint digest — the index key. Both sweep tasks
        # and serial runs record under this same key, so a config first run as a
        # sweep task hits here when re-run serially (sweep items are first-class).
        repos, data, _ = extract_tracking_info(cfg)
        try:
            fp = compute_fingerprint(cfg, repos=repos, data=data)
        except Exception as e:
            logger.warning(f"Could not compute fingerprint for lookup: {e}")
            fp = None

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

        fallback = flexlock_config.get_env_bool("FLEXLOCK_INDEX_FALLBACK", True)

        for search_root in search_dirs:
            logger.debug(f"Searching for matching runs in: {search_root}")
            root_path = Path(search_root)

            # 1. Fast path: single indexed lookup by fingerprint.
            if fp:
                row = index.lookup(root_path, fp)
                if row is not None:
                    resolved = index.verify_and_resolve(root_path, row)
                    if resolved is not None:
                        logger.success(f"⚡ Cache Hit (index)! {resolved}")
                        return resolved

            # 2. Fallback: legacy glob scan for runs predating the index. On a
            #    hit, backfill the index so the slow path self-eliminates.
            if fallback and root_path.exists():
                match = self._glob_scan_match(
                    cfg, root_path, match_include, match_exclude
                )
                if match is not None:
                    if fp:
                        index.record_run_lock(match, fp)
                    logger.success(f"⚡ Cache Hit (glob)! {match}")
                    return match

        return None

    def _glob_scan_match(
        self, cfg, root_path, match_include, match_exclude
    ) -> Optional[Path]:
        """Legacy O(N) content scan used only as an index fallback (RunDiff)."""
        from .record import iter_run_dirs, load_record

        fingerprint = self._generate_fingerprint(cfg)
        for run_dir in iter_run_dirs(root_path):
            try:
                candidate_snapshot = load_record(run_dir)
                if candidate_snapshot is None:
                    continue

                proposed_save_dir = fingerprint.get("config", {}).get("save_dir")
                candidate_save_dir = candidate_snapshot.get("config", {}).get(
                    "save_dir"
                )

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
                    # Require run.complete — interrupted runs are not cache hits.
                    if not (run_dir / "run.complete").exists():
                        logger.debug(
                            f"Match at {run_dir} has no run.complete; skipping"
                        )
                        continue
                    return run_dir
                else:
                    logger.debug(f"No match for run at: {run_dir}: {differ.diffs}")
            except Exception as e:
                logger.debug(f"Failed to read/compare {run_dir}: {e}")
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

        return self._load_cached_result(match_dir, cfg)

    def _load_cached_result(self, match_dir: Path, cfg: DictConfig) -> ExecutionResult:
        """Build a CACHED ExecutionResult from an existing run directory."""
        result_data = None

        # Try results.json
        results_file = match_dir / "results.json"
        if results_file.exists():
            with open(results_file, "r") as f:
                result_data = json.load(f)

        # Fall back to the run record (run.lock or task DB)
        if result_data is None:
            from .record import load_record

            lock_data = load_record(match_dir)
            if lock_data is not None:
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
        tag: "str | None" = None,
        timeout: "int | None" = None,
        note: "str | None" = None,
        save_dir_policy: "str | None" = None,
        task_record: "str | None" = None,
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
            tag: Human-readable label for this sweep's rows in the shared task
                DB (e.g. ``"extract"`` or ``"collocate"``). Passed through to
                ``ParallelExecutor`` so workers and the status CLI can scope to
                it. When ``None`` a deterministic hash is auto-generated.
            note: Free-text intent recorded as a top-level ``note:`` key in
                ``run.lock`` (sibling of ``timestamp``/``config``). Never enters
                the fingerprint, so it can't perturb caching. For sweeps the note
                lands on the master ``run.lock`` only; sweep items inherit it for
                display via their ``.flexlock_marker`` → master lookup.
            save_dir_policy: What to do when ``config.save_dir`` is already
                occupied by a previous run (contains ``run.lock``), applied
                once at submit time, after the ``smart_run`` cache check:
                ``None``/``"raise"`` (default) refuses and raises;
                ``"increment"`` versions the dir (``run`` → ``run_0000``,
                claimed atomically); ``"overwrite"`` deletes the occupied
                dir's contents first (never touches a dir without
                ``run.lock``); ``"skip"`` returns the existing complete
                run's result without executing; ``"unsafe"`` runs in place
                with no check; ``"timestamp"`` appends
                ``config.TIMESTAMP_FORMAT``. ``force=True`` bypasses the
                default guard (explicit in-place rerun). Replaces the
                ``${vinc:}`` / ``${now:}`` resolvers. For sweeps the policy
                applies once to the sweep root; items nest beneath it, and
                ``"skip"`` means resume (reuse complete items, run the rest).
            task_record: Where each sweep task's record goes: ``"dir"`` (default,
                or ``$FLEXLOCK_TASK_RECORD``) writes a full ``run.lock`` into the
                task's save_dir; ``"db"`` keeps it in the task DB only (fewer
                files for very large sweeps). Single runs, including HPC ones,
                always get a ``run.lock``. Readers find either through
                :func:`flexlock.record.load_record`.

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
            # In order; key=@name swaps the node (see utils.apply_overrides).
            apply_overrides(config, overrides, module=self.override_module)
        if sweep:
            # "@name" sweep values swap in a named config (replace, not merge).
            sweep = [expand_swaps(item, self.override_module) for item in sweep]

        # Fix which run each ${run:...} means now, at submit (a no-op when the
        # CLI already did it); records the resolved runs as lineage.
        freeze_run_refs(config)

        # Bake save_dir to a concrete string exactly once. Done here (not
        # lazily during config reads) so run.lock and run.complete always land
        # in the same directory. The policy itself (naming / collision guard)
        # is applied later, after the smart_run cache check and the
        # side-effect-free previews (print_config / dry_run).
        from .save_dir import SKIP, apply_save_dir_policy, resolve_save_dir

        resolve_save_dir(config)

        if print_config:
            # When a sweep is given, preview each item's merged config so
            # the user can verify per-item interpolations resolve correctly
            # before launching.
            if sweep:
                from .utils import merge_task_into_cfg

                for i, override in enumerate(sweep):
                    # Mirror _submit_sweep exactly (merge → freeze) so the
                    # preview matches what will actually execute.
                    item_cfg = merge_task_into_cfg(config, override, sweep_target)
                    item_cfg = freeze_deferred(item_cfg)
                    print(f"# --- sweep item {i} ---")
                    _print_compiled_config(item_cfg)
            else:
                _print_compiled_config(config)
            return None

        if force:
            # Invalidate the single-run cache marker. For sweeps the per-item
            # markers and task DB are reset inside _submit_sweep (2.4).
            if not sweep:
                save_dir = Path(config.get("save_dir", "outputs/job"))
                marker = save_dir / "run.complete"
                if marker.exists():
                    logger.info(f"Force flag enabled: invalidating cache at {save_dir}")
                    marker.unlink()
            smart_run = False

        # Handle sweep execution
        if sweep:
            # A sweep runs each item in its own worker process; `isolated`
            # (spawn a subprocess for a *single* run) can't be honoured here.
            # Fail loudly rather than silently dropping it (issue 16).
            if isolated:
                from .exceptions import FlexLockConfigError

                raise FlexLockConfigError(
                    "isolated=True is not supported with sweep=... — sweep items "
                    "already execute in separate worker processes."
                )
            # A naming policy fixes the sweep root before items are built;
            # guard policies are enforced per item inside _submit_sweep, after
            # the per-item cache check ('skip' there means resume: reuse
            # complete items, rerun crashed ones).
            from .save_dir import NAMING_POLICIES, validate_policy

            validate_policy(save_dir_policy)
            if save_dir_policy in NAMING_POLICIES:
                apply_save_dir_policy(config, save_dir_policy, force=force)
                # Items are fresh under the freshly named root; keep the
                # default guard as a backstop.
                item_policy = "raise"
            else:
                item_policy = save_dir_policy or "raise"
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
                tag=tag,
                force=force,
                timeout=timeout,
                note=note,
                item_policy=item_policy,
                task_record=task_record,
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

        # Naming / collision-guard policy — after the cache check (a hit never
        # claims or cleans anything) and after the previews (no side effects).
        if apply_save_dir_policy(config, save_dir_policy, force=force) == SKIP:
            match_dir = Path(str(config.save_dir))
            logger.info(f"save_dir_policy='skip': reusing result from {match_dir}")
            return self._load_cached_result(match_dir, config)

        if use_hpc:
            # Execute via HPC backend
            logger.info(f"Submitting to HPC backend...")

            # Use ParallelExecutor with a single task
            from .parallel import ParallelExecutor

            save_dir = config.get("save_dir", "outputs/job")
            if force:
                # The executor queues with INSERT OR IGNORE: a 'done' row left
                # by the previous run would make run() a no-op.
                _reset_task_db(Path(str(save_dir)))
            # Resolve _snapshot_ while config still has its parent chain: the
            # executor_cfg below is re-rooted, so relative refs (${...key})
            # inside _snapshot_ would no longer reach the stage node.
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
                tasks=[config],  # Single task as a list
                task_target=None,
                cfg=executor_cfg,
                n_jobs=flexlock_config.DEFAULT_N_JOBS,
                pbs_config=pbs_config,
                slurm_config=slurm_config,
                local_workers=None,
                tag=tag,
                note=note,
                task_record="dir",
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
                if force:
                    _reset_task_db(Path(str(save_dir)))
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
                    tag=tag,
                    note=note,
                    task_record="dir",
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

            # Single deferred-resolution point (local single-run path): fire
            # the deferred resolvers (run_lock/latest) once and detach into a
            # plain config. Re-wrapping prevents instantiate()'s internal
            # config.copy() — a fresh instance with an empty resolver cache —
            # from re-firing anything after snapshot() has run.
            try:
                from .resolvers import resolve_deferred

                config = resolve_deferred(config)
            except Exception as exc:
                logger.warning(f"Could not fully resolve config before execution: {exc}")

            # Compute the fingerprint once (index key), stored in run.lock so
            # `flexlock reindex` can rebuild the index from disk.
            run_fp = None
            if "save_dir" in config:
                try:
                    run_fp = compute_fingerprint(config, repos=repos, data=data)
                except Exception as exc:
                    logger.warning(f"Could not compute run fingerprint: {exc}")

            # Create snapshot before execution
            if "save_dir" in config:
                snapshot(
                    config, repos=repos, data=data, prevs=prevs,
                    fingerprint=run_fp, note=note,
                )

            # Execute the function
            logger.info(f"Executing configuration...")
            run_func = instantiate
            if debug:
                from .debug import debug_on_fail

                run_func = debug_on_fail(run_func)
            try:
                result = run_func(config)
            except Exception as exc:
                # Record a failure sidecar next to run.lock so triage doesn't
                # need to re-run. The user's exception still propagates unwrapped
                # (docs §12); write_error never raises. KeyboardInterrupt is
                # deliberately not caught — a bare run.lock is the interrupted
                # signature.
                if "save_dir" in config:
                    RunRecord(config.save_dir).write_error(exc)
                    record_code_drift(config.save_dir)
                raise

            # Save results if save_dir is specified
            save_dir = config.get("save_dir", ".")
            if "save_dir" in config:
                record = RunRecord(save_dir)
                try:
                    record.write_results(result)
                except Exception as e:
                    logger.warning(
                        f"Could not save results to {record.results_path}: {e}"
                    )
                record_code_drift(save_dir)
                record.mark_complete(result=result)
                from .presets import link_run

                link_run(save_dir, config)
                # Record the completed run in the project-wide index (2.2).
                if run_fp:
                    index.record_run_lock(save_dir, run_fp)

            return ExecutionResult(
                save_dir=str(save_dir), status="SUCCESS", result=result, cfg=config
            )

    def check(
        self,
        config=None,
        *,
        sweep: "List[Dict] | None" = None,
        sweep_target: "str | None" = None,
        overrides: "dict | List[str] | None" = None,
        merge: "str | Path | dict | None" = None,
    ) -> "List[dict]":
        """Preflight: fully resolve the config (and every sweep item) without
        touching the filesystem or executing anything.

        Mirrors submit's merge → freeze pipeline, but runs under the freeze
        stubs so no resolver fires (``vinc``/``now`` take no ``mkdir``,
        ``run_lock``/``latest`` read nothing). Every unresolvable interpolation
        is reported — not just the first — as a dict with ``item`` (sweep index
        or ``None``), ``full_key``, and ``error``.

        Returns an empty list when everything resolves.
        """
        from .utils import merge_task_into_cfg
        from .resolvers import frozen_resolvers
        from omegaconf.errors import OmegaConfBaseException

        # Normalize config exactly like submit (but never mutate the caller's).
        if config is None:
            config = self.defaults
        elif isinstance(config, str):
            config = self.get(config)
        if not isinstance(config, DictConfig):
            config = OmegaConf.create(config)
        config = config.copy()
        if merge is not None:
            if isinstance(merge, (str, Path)):
                config.merge_with(OmegaConf.load(str(merge)))
            else:
                config.merge_with(OmegaConf.create(merge))
        if overrides is not None:
            # In order; key=@name swaps the node (see utils.apply_overrides).
            apply_overrides(config, overrides, module=self.override_module)
        if sweep:
            # "@name" sweep values swap in a named config (replace, not merge).
            sweep = [expand_swaps(item, self.override_module) for item in sweep]

        if sweep:
            items = [
                (i, merge_task_into_cfg(config, ov, sweep_target))
                for i, ov in enumerate(sweep)
            ]
        else:
            items = [(None, config)]

        errors: List[dict] = []
        with frozen_resolvers():
            for idx, item in items:
                detached = OmegaConf.create(
                    OmegaConf.to_container(item, resolve=False, throw_on_missing=False)
                )
                # Resolve leaf-by-leaf so every failure is reported, not only
                # the first one OmegaConf.resolve would raise on.
                for path, val in _leaf_paths(
                    OmegaConf.to_container(detached, resolve=False, throw_on_missing=False)
                ):
                    if not (isinstance(val, str) and "${" in val):
                        continue
                    try:
                        OmegaConf.select(detached, path, throw_on_missing=True)
                    except OmegaConfBaseException as e:
                        errors.append(
                            {
                                "item": idx,
                                "full_key": getattr(e, "full_key", None) or path,
                                "error": str(e),
                            }
                        )
        return errors

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

        The sweep root is taken from ``sweep_root`` when provided, otherwise
        from the parent of the first (already merged and frozen) item's
        save_dir — the same directory the tasks DB lives in. Validation only
        ever touches the merged items, never ``base_config.save_dir`` (which
        may still carry a per-item ``${.variable}`` that is unresolvable until
        an item supplies it).
        """
        from .exceptions import FlexLockValidationError

        if not merged_items:
            return

        # When the user explicitly provides a sweep_root they've opted out of
        # the containment constraint — trust them and skip validation.
        if sweep_root is not None:
            return

        # Derive the sweep root from the merged items (concrete save_dirs).
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

    @staticmethod
    def _pipeline_stage_dirs(item) -> "list[str]":
        """Concrete save_dirs of one pipeline item's stages (must all be set)."""
        from .exceptions import FlexLockValidationError

        dirs = []
        for j, stage in enumerate(item):
            sd = stage.get("save_dir") if hasattr(stage, "get") else None
            if sd is None:
                raise FlexLockValidationError(
                    f"Pipeline stage {j} has no save_dir. Every stage of a "
                    f"composite pipeline task needs a concrete save_dir (the "
                    f"task DB and lineage markers are anchored to it)."
                )
            dirs.append(str(sd))
        return dirs

    def _pipeline_roots(self, items, sweep_root):
        """Derive (master_root, item_roots) for a pipeline submission.

        Each item's root is the common path of its stage ``save_dir``s (the
        pipeline dir). The master root — where the task DB lives — is the
        ``sweep_root`` when given, the item root for a single item, and the
        common path of the item roots otherwise. Without an explicit
        ``sweep_root``, multi-item pipelines must nest under the first item's
        parent (mirroring ``_validate_sweep_save_dirs``).
        """
        import os

        from .exceptions import FlexLockValidationError

        item_roots = [
            Path(os.path.commonpath(
                [os.path.abspath(sd) for sd in self._pipeline_stage_dirs(item)]
            ))
            for item in items
        ]

        if sweep_root is not None:
            return Path(sweep_root), item_roots

        if len(item_roots) == 1:
            return item_roots[0], item_roots

        expected_root = item_roots[0].parent
        offenders = [
            (i, root)
            for i, root in enumerate(item_roots)
            if not root.is_relative_to(expected_root)
        ]
        if offenders:
            lines = [f"  item {i}: pipeline dir {root}" for i, root in offenders]
            raise FlexLockValidationError(
                f"Pipeline item save_dirs must nest under a common root "
                f"({expected_root}); the tasks DB and lineage markers live "
                f"there. Offending items:\n"
                + "\n".join(lines)
                + f"\n\nTo keep the current save_dirs, use --sweep-root "
                f"<common_parent> (e.g. --sweep-root {offenders[0][1].parent})."
            )
        return Path(os.path.commonpath(item_roots)), item_roots

    def _collect_pipeline_results(
        self, indices, queued_items, queued_tasks, db_path, tag
    ) -> "list[tuple[int, list[ExecutionResult]]]":
        """Per-stage ExecutionResults for queued pipeline items.

        The composite row's terminal status maps to the item; each stage is
        classified from its dir: ``run.complete`` → SUCCESS (a stage that ran
        before a later failure stays SUCCESS), the failing stage (``run.error``
        present on a failed row) → FAILED with the row's error, unreached
        stages → SUBMITTED (or INTERRUPTED when the row was interrupted).
        """
        from .taskdb import get_all_tasks, _hash_task

        by_id = {
            t["task_id"]: t
            for t in get_all_tasks(db_path, tags=[tag] if tag else None)
        }
        out = []
        for idx, item, task_dict in zip(indices, queued_items, queued_tasks):
            row = by_id.get(_hash_task(task_dict))
            db_status = row["status"] if row else None
            stage_results = []
            for stage_cfg in item:
                sd = Path(str(stage_cfg.get("save_dir")))
                record = RunRecord(sd)
                if record.complete_path.exists():
                    stage_results.append(
                        ExecutionResult(
                            save_dir=str(sd),
                            status=Status.SUCCESS,
                            result=record.load_results(),
                            cfg=stage_cfg,
                        )
                    )
                elif db_status == "failed" and record.error_path.exists():
                    stage_results.append(
                        ExecutionResult(
                            save_dir=str(sd),
                            status=Status.FAILED,
                            cfg=stage_cfg,
                            error=row.get("error") if row else None,
                        )
                    )
                elif db_status == "interrupted":
                    stage_results.append(
                        ExecutionResult(
                            save_dir=str(sd),
                            status=Status.INTERRUPTED,
                            cfg=stage_cfg,
                        )
                    )
                else:
                    stage_results.append(
                        ExecutionResult(
                            save_dir=str(sd), status=Status.SUBMITTED, cfg=stage_cfg
                        )
                    )
            out.append((idx, stage_results))
        return out

    def submit_pipeline(
        self,
        items: "List[List[DictConfig]]",
        *,
        n_jobs: int = 1,
        smart_run: bool = False,
        search_dirs: List[str] = None,
        slurm_config: str = None,
        pbs_config: str = None,
        wait: bool = True,
        sweep_root: "str | None" = None,
        tag: "str | None" = None,
        force: bool = False,
        timeout: "int | None" = None,
        note: "str | None" = None,
        save_dir_policy: "str | None" = None,
        debug: bool = False,
        dry_run: bool = False,
    ) -> "List[List[ExecutionResult]] | None":
        """Submit composite pipeline tasks: one task per item, stages in order.

        Each *item* is a list of already-compiled, frozen stage configs (the
        caller applied :func:`freeze_deferred`; deferred resolvers fire on the
        worker at stage start). One item becomes one composite task in the
        sweep task DB (``{"_stages_": [...]}``): the worker runs its stages
        sequentially, so intra-item ordering holds by construction, while
        parallelism (local ``n_jobs``, Slurm/PBS array workers) fans out
        across items.

        Composite tasks are self-contained — the base config is never
        re-merged into them at dequeue time.

        Known limitation: all stages of an item run inside one scheduler job /
        worker slot, so per-stage HPC resource configs are not possible.

        Args:
            items: ``items[i][j]`` is the ``j``-th stage config of item ``i``.
            n_jobs: Parallel workers fanning out across items.
            smart_run: Driver-side cache check — an item whose every stage
                cache-hits returns CACHED without queueing; partial hits queue
                the item with stage-level resume (``_skip_complete_``).
            search_dirs: Directories searched for cached runs (smart_run).
            slurm_config / pbs_config: Path to HPC backend YAML.
            wait: Block until completion (HPC). ``False`` returns SUBMITTED
                skeleton results.
            sweep_root: Override the master root hosting the task DB; also
                opts out of the containment validation.
            tag / note / timeout: As in :meth:`submit`.
            force: Invalidate every stage's completion markers and reset the
                task DB so all items rerun.
            save_dir_policy: Collision guard applied per stage dir before
                queueing — ``raise`` (default, unless ``force``),
                ``overwrite``, ``skip`` (stage-level resume), ``unsafe``.
                Naming policies (``increment``/``timestamp``) don't compose
                with pre-baked cross-stage paths and are rejected.
            debug: Post-mortem debugger (local in-process execution only).
            dry_run: With an HPC backend, render the submission script and
                return ``None`` without queueing anything.

        Returns:
            ``results[i][j]`` is the :class:`ExecutionResult` of item ``i``'s
            stage ``j`` (or ``None`` for ``dry_run``).
        """
        from .exceptions import FlexLockValidationError
        from .parallel import ParallelExecutor
        from .save_dir import (
            NAMING_POLICIES,
            clean_run_dir,
            is_occupied,
            occupied_error,
            validate_policy,
        )

        if not items:
            return []

        validate_policy(save_dir_policy)
        if save_dir_policy in NAMING_POLICIES:
            raise FlexLockValidationError(
                f"save_dir_policy={save_dir_policy!r} is not supported for "
                f"pipelines: naming policies rewrite save_dir at submit time, "
                f"which breaks the pre-baked cross-stage paths of the frozen "
                f"stage configs. Use 'overwrite', 'skip', 'unsafe', or bake "
                f"a fresh pipeline dir into the config instead."
            )
        item_policy = save_dir_policy or "raise"

        # Master root (task DB home) + containment validation.
        master_root, _item_roots = self._pipeline_roots(items, sweep_root)

        use_hpc = pbs_config is not None or slurm_config is not None

        if dry_run:
            if not use_hpc:
                logger.info("dry_run is a no-op for local execution.")
                return None
            self._preview_hpc_script(
                OmegaConf.create({"save_dir": str(master_root)}),
                slurm_config,
                pbs_config,
            )
            return None

        # force: reset every stage's completion markers and the task DB so the
        # pending_count==0 resume short-circuit can't kick in.
        if force:
            for item in items:
                for sd in self._pipeline_stage_dirs(item):
                    d = Path(sd)
                    (d / "run.complete").unlink(missing_ok=True)
                    (d / "results.json").unlink(missing_ok=True)
            _reset_task_db(master_root)
            logger.info(
                f"Force flag enabled: reset pipeline task DB under {master_root}"
            )
            smart_run = False

        # Stage-level resume on the worker: requested via smart_run/check-exists
        # or the 'skip' guard policy.
        skip_complete = bool(smart_run) or item_policy == "skip"

        # Driver-side cache check: items whose every stage cache-hits return
        # CACHED without queueing. Partial hits queue with stage-level resume.
        cached_results: list = []
        to_queue: list = []  # (index, item)
        for i, item in enumerate(items):
            if smart_run:
                matches = [
                    self._find_matching_run(stage_cfg, search_dirs)
                    for stage_cfg in item
                ]
                if all(m is not None for m in matches):
                    logger.info(f"Pipeline item {i}: all stages cached — skipping")
                    cached_results.append(
                        (i, [
                            self._load_cached_result(m, stage_cfg)
                            for m, stage_cfg in zip(matches, item)
                        ])
                    )
                    continue
            to_queue.append((i, item))

        # Collision guard, per stage dir, driver-side, before queueing.
        if item_policy != "unsafe":
            for i, item in to_queue:
                for sd in self._pipeline_stage_dirs(item):
                    if not is_occupied(sd):
                        continue
                    if item_policy == "overwrite":
                        clean_run_dir(sd)
                    elif item_policy == "skip":
                        pass  # worker resumes past complete stages
                    elif force:
                        pass  # explicit in-place rerun
                    else:
                        raise occupied_error(str(sd), sweep_item=i)

        results: list = []
        if to_queue:
            # Serialize each item as a self-contained composite task dict.
            queued_tasks = []
            for _, item in to_queue:
                task_dict = {
                    "_stages_": [
                        OmegaConf.to_container(
                            stage, resolve=False, throw_on_missing=False
                        )
                        for stage in item
                    ]
                }
                if skip_complete:
                    task_dict["_skip_complete_"] = True
                queued_tasks.append(task_dict)

            executor_cfg = OmegaConf.create(
                {"save_dir": str(master_root), "_snapshot_": {}}
            )
            func = instantiate
            if debug:
                if use_hpc or n_jobs > 1:
                    logger.warning(
                        "debug=True is ignored for parallel/HPC pipeline "
                        "execution (post-mortem PDB needs an in-process run)."
                    )
                else:
                    from .debug import debug_on_fail

                    func = debug_on_fail(func)

            executor = ParallelExecutor(
                func=func,
                tasks=queued_tasks,
                task_target=None,
                cfg=executor_cfg,
                n_jobs=n_jobs,
                pbs_config=pbs_config,
                slurm_config=slurm_config,
                local_workers=n_jobs if not use_hpc else None,
                tag=tag,
                note=note,
            )
            executor.run(wait=wait, timeout=timeout)

            results = self._collect_pipeline_results(
                [i for i, _ in to_queue],
                [item for _, item in to_queue],
                queued_tasks,
                executor.db_path,
                executor.tag,
            )

        all_results = cached_results + results
        all_results.sort(key=lambda x: x[0])
        return [item_results for _, item_results in all_results]

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

    @staticmethod
    def collect_results(indices, task_configs, db_path, tag) -> list:
        """Build per-item ExecutionResults from the task DB's terminal state.

        Replaces the old blanket ``status="SUCCESS"`` — a task that raised is
        now reported as ``FAILED`` with its traceback, so a sweep result set
        faithfully reflects what happened (issue 2).
        """
        from .taskdb import get_all_tasks, _hash_task

        by_id = {
            t["task_id"]: t
            for t in get_all_tasks(db_path, tags=[tag] if tag else None)
        }
        status_map = {
            "done": "SUCCESS",
            "failed": "FAILED",
            "interrupted": "INTERRUPTED",
        }
        out = []
        for idx, cfg in zip(indices, task_configs):
            save_dir = str(cfg.get("save_dir", "."))
            row = by_id.get(_hash_task(cfg))
            db_status = row["status"] if row else None
            status = status_map.get(db_status, "SUBMITTED")

            result_data = None
            error = None
            if status == "SUCCESS":
                result_data = RunRecord(save_dir).load_results()
                if result_data is None and row:
                    result_data = row.get("result") or None
            elif status == "FAILED":
                error = row.get("error") if row else None

            out.append(
                (
                    idx,
                    ExecutionResult(
                        save_dir=save_dir,
                        status=status,
                        result=result_data,
                        cfg=cfg,
                        error=error,
                    ),
                )
            )
        return out

    @staticmethod
    def _sweep_db_dir(merged_items, sweep_root) -> "Path | None":
        """Directory that hosts the sweep's task DB (mirrors the parallel path)."""
        if sweep_root is not None:
            return Path(sweep_root)
        for _, cfg in merged_items:
            if "save_dir" in cfg:
                return Path(cfg.save_dir).parent
        return None

    def _reset_sweep_for_force(self, merged_items, sweep_root) -> None:
        """Invalidate per-item markers and the task DB so a forced sweep reruns."""
        # Per-item completion markers + results (so RunRecord/index see fresh runs).
        for _, cfg in merged_items:
            if "save_dir" in cfg:
                d = Path(cfg.save_dir)
                (d / "run.complete").unlink(missing_ok=True)
                (d / "results.json").unlink(missing_ok=True)

        # Task DB (its pending_count==0 short-circuit would otherwise resume).
        db_dir = self._sweep_db_dir(merged_items, sweep_root)
        if db_dir is not None:
            _reset_task_db(db_dir)
            logger.info(f"Force flag enabled: reset sweep task DB under {db_dir}")

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
        tag: "str | None" = None,
        force: bool = False,
        timeout: "int | None" = None,
        note: "str | None" = None,
        item_policy: str = "raise",
        task_record: "str | None" = None,
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
            # Merge the sweep item into the base FIRST, so item-injected keys
            # (e.g. `variable`) exist before any resolution — then freeze.
            sweep_cfg = merge_task_into_cfg(base_config, override, sweep_target)
            # Eager-resolve everything self-contained for DB serialization,
            # while preserving deferred resolvers (run_lock/latest) as call
            # strings so they fire once, on the worker, at stage start.
            # ${run:} per item first, so its lineage lands in the item.
            freeze_run_refs(sweep_cfg)
            sweep_cfg = freeze_deferred(sweep_cfg)
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

        # Force: reset the per-item completion markers *and* the task DB so every
        # item re-executes. Unlinking only the base marker (the old behaviour)
        # missed both the per-item markers and the DB's pending_count==0
        # resume short-circuit, so a forced sweep silently re-used cached
        # tasks (issue 15).
        if force:
            self._reset_sweep_for_force(merged_items, sweep_root)

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

        # Collision guard, per item, after the cache check (a cache hit never
        # trips the guard). Applied here — before anything is queued — so a
        # refusal aborts the whole sweep up front. Items whose save_dir is
        # occupied by a previous run are handled per `item_policy`; items of
        # *this* sweep sharing one save_dir don't trip it (nothing is occupied
        # until execution starts).
        if item_policy != "unsafe":
            from .record import MARKER_NAME
            from .save_dir import clean_run_dir, is_complete, is_occupied, occupied_error

            still_to_run = []
            for i, sweep_cfg in configs_to_run:
                item_dir = sweep_cfg.get("save_dir")
                # A dir with a .flexlock_marker belongs to a sweep task: it is
                # managed by its task DB (resume via the DB, as before task
                # dirs carried a run.lock), not by the collision guard.
                if (
                    item_dir is None
                    or not is_occupied(item_dir)
                    or (Path(item_dir) / MARKER_NAME).exists()
                ):
                    still_to_run.append((i, sweep_cfg))
                elif item_policy == "overwrite":
                    clean_run_dir(item_dir)
                    still_to_run.append((i, sweep_cfg))
                elif item_policy == "skip":
                    # Resume: reuse complete items, rerun crashed ones in place.
                    if is_complete(item_dir):
                        logger.info(f"Sweep {i}: skip — reusing {item_dir}")
                        cached_results.append(
                            (i, self._load_cached_result(Path(item_dir), sweep_cfg))
                        )
                    else:
                        still_to_run.append((i, sweep_cfg))
                elif force:
                    still_to_run.append((i, sweep_cfg))
                else:
                    raise occupied_error(str(item_dir), sweep_item=i)
            configs_to_run = still_to_run

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
                    tag=tag,
                    note=note,
                    task_record=task_record,
                )

                # Run the sweep (executor handles waiting based on wait parameter)
                success = executor.run(wait=wait, timeout=timeout)

                # Collect real per-task statuses from the task DB (issue 2).
                results.extend(
                    self.collect_results(
                        indices, task_configs, executor.db_path, executor.tag
                    )
                )
            else:
                # Sequential execution (no backend, n_jobs=1)
                for i, cfg in configs_to_run:
                    logger.info(f"Executing sweep {i}/{len(sweep)}")
                    # Guard already applied above — run items unguarded so
                    # same-save_dir items of one sweep behave as before.
                    result = self.submit(
                        cfg,
                        sweep=None,
                        smart_run=False,
                        wait=True,
                        debug=debug,
                        force=force,
                        save_dir_policy="unsafe",
                    )
                    results.append((i, result))

        # Combine cached and new results, sorted by index
        all_results = cached_results + results
        all_results.sort(key=lambda x: x[0])

        return [result for _, result in all_results]
