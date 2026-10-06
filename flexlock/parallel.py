"""Manages parallel task execution for FlexLock."""

from pathlib import Path
from omegaconf import OmegaConf, DictConfig
from loguru import logger
import hashlib
from flexlock.taskdb import queue_tasks, pending_count, get_status_counts_by_tag
from flexlock.taskdb import _hash_task as _taskdb_hash_task
from flexlock.worker import worker_loop
from flexlock.backends.slurm import SlurmBackend
from flexlock.backends.pbs import PBSBackend
import multiprocessing
from multiprocessing import Process
import yaml
from typing import Any, List
from flexlock.snapshot import snapshot
from flexlock.utils import extract_tracking_info, collect_task_repos
from flexlock import config
from flexlock.exceptions import WorkerExecutionError


def load_tasks(tasks: str, tasks_key: str, cfg: DictConfig) -> List[Any]:
    """Load tasks from a file or from the config."""
    if tasks:
        all_tasks = []
        for t in tasks:
            p_tasks = Path(t)
            if not p_tasks.exists():
                raise FileNotFoundError(f"Tasks file not found: {t}")
            if p_tasks.suffix == ".txt":
                all_tasks.extend(
                    [line.strip() for line in p_tasks.read_text().splitlines()]
                )
            elif p_tasks.suffix in [".yaml", ".yml"]:
                with p_tasks.open() as f:
                    all_tasks.extend(yaml.safe_load(f))
            else:
                raise ValueError(f"Unsupported tasks file format: {p_tasks.suffix}")
        return all_tasks
    elif tasks_key:
        return OmegaConf.select(cfg, tasks_key)
    return []


def _default_tag(tasks, save_dir) -> str:
    """Deterministic 12-hex-char tag for a sweep.

    Stable across re-runs of the same (tasks, save_dir) pair, so resume-aware
    INSERT OR IGNORE dedup works correctly when a sweep is restarted.
    """
    task_ids = "".join(sorted(_taskdb_hash_task(t) for t in tasks))
    return hashlib.sha1(f"{task_ids}{save_dir}".encode()).hexdigest()[:12]


def _shared_product_roots(cfg, tasks, task_target):
    """Find roots reused by distinct items and reject declared output collisions."""
    from collections import Counter
    from .utils import merge_task_into_cfg
    from .outputs import _contracts
    from .exceptions import FlexLockValidationError

    stages = []
    for task in tasks:
        item = merge_task_into_cfg(cfg, task, task_target)
        raw_stages = item.get('_stages_', [item])
        for raw in raw_stages:
            # Composite stages resolve their own root references on the worker.
            # Detach them here too; ${item} must not bind to the wrapper root.
            stage = OmegaConf.create(OmegaConf.to_container(raw, resolve=False)
                                     if OmegaConf.is_config(raw) else raw)
            sd = OmegaConf.to_container(stage, resolve=False).get('save_dir')
            if sd and '${' not in str(sd):
                stages.append((str(Path(sd).resolve()), stage))
    counts = Counter(sd for sd, _ in stages)
    shared = sorted(sd for sd, count in counts.items() if count > 1)
    outputs = []
    for sd, stage in stages:
        if sd not in shared:
            continue
        for path, _ in _contracts(stage, sd).values():
            resolved = path.resolve()
            if any(resolved == previous or resolved in previous.parents or previous in resolved.parents
                   for previous in outputs):
                raise FlexLockValidationError(f'Shared-root items declare overlapping output {resolved}; '
                                              'give each item disjoint products')
            outputs.append(resolved)
    return shared


class ParallelExecutor:
    """Manages the execution of tasks in parallel using a centralized task queue.

    This class orchestrates task execution across different backends (local, Slurm, PBS)
    by interacting with a SQLite database for task management. It supports dynamic task
    distribution (pull model) and result aggregation.
    """

    def __init__(
        self,
        func,
        tasks: List[Any],
        task_target: str | None,
        cfg: DictConfig,
        n_jobs: int = 1,
        slurm_config: str | None = None,
        pbs_config: str | None = None,
        local_workers: int | None = None,
        isolated: bool = False,
        tag: str | None = None,
        note: str | None = None,
        task_record: str | None = None,
        after=None,
    ):
        """Initializes the ParallelExecutor.

        Args:
            func: The function to execute for each task.
            tasks: A list of tasks to be executed.
            task_target: The OmegaConf path to merge task-specific configurations into.
            cfg: The base OmegaConf configuration.
            n_jobs: Number of parallel jobs for local execution.
            slurm_config: Path to the Slurm configuration file.
            after: Scheduler jobs that must finish successfully before this job.
            pbs_config: Path to the PBS configuration file.
            local_workers: Number of local worker processes to spawn.
            isolated: If True, always run in a spawned subprocess even when n_jobs=1.
                Use this for stages that initialise GPU/CUDA so that the CUDA context
                is confined to the child and never leaks into the parent process.
            tag: Tag scoping this sweep's rows in the shared task DB.  When ``None``
                a deterministic hash of the task list + save_dir is used so that
                re-runs reuse the same tag (resume-safe).  Pass an explicit human-
                readable string (e.g. ``"extract"``) to target this sweep from the
                ``flexlock-worker --tags`` CLI.
            task_record: ``"dir"`` (default, ``$FLEXLOCK_TASK_RECORD``) writes
                each task's full run.lock into its save_dir; ``"db"`` keeps it
                in the task DB only. Stored in the master run.lock so workers
                attached later follow it.
        """
        from .backends.dependencies import validate_after

        after = validate_after(after, slurm_config, pbs_config)
        self.func = func
        self.tasks = tasks
        self.task_target = task_target
        self.cfg = cfg
        self.n_jobs = n_jobs
        self.local_workers = local_workers
        self.isolated = isolated
        self.note = note
        self.task_record = task_record or config.default_task_record()
        if self.task_record not in config.TASK_RECORD_MODES:
            raise ValueError(
                f"task_record must be one of {config.TASK_RECORD_MODES}, "
                f"got {self.task_record!r}"
            )

        self.save_dir = Path(cfg.save_dir)
        self.db_path = self.save_dir / "run.lock.tasks.db"

        # A cached prefix can leave only one new item to enqueue. Include the
        # existing DB so appending it does not turn its shared root into a
        # single-run receipt directory or overwrite the campaign master.
        all_tasks = {_taskdb_hash_task(task): task for task in tasks}
        if self.db_path.exists():
            from .record import list_task_records
            for row in list_task_records(self.db_path):
                if row['status'] == 'done':
                    all_tasks.setdefault(row['task_id'], row['task'])
        self.shared_save_dirs = _shared_product_roots(cfg, list(all_tasks.values()), task_target)
        from .record import read_lock
        previous = read_lock(self.save_dir) or {}
        self.shared_save_dirs = sorted(set(self.shared_save_dirs) | set(previous.get('shared_save_dirs', [])))

        self.tag = tag if tag is not None else _default_tag(tasks, self.save_dir)

        if self.db_path.exists():
            existing_by_tag = get_status_counts_by_tag(self.db_path)
            existing_tags = set(existing_by_tag.keys())
            if existing_tags and self.tag not in existing_tags:
                # Different sweeps coexisting in one DB — expected, log at INFO.
                logger.info(
                    f"Task DB already exists with tag(s) {existing_tags!r}: {self.db_path}\n"
                    f"  New sweep (tag={self.tag!r}) will add {len(tasks)} rows alongside them."
                )
            elif self.tag in existing_tags:
                logger.info(
                    f"Resuming sweep (tag={self.tag!r}) in existing DB: {self.db_path}\n"
                    f"  Tasks with matching hashes will be skipped (INSERT OR IGNORE)."
                )
            else:
                logger.warning(
                    f"Task DB already exists: {self.db_path}\n"
                    f"  New sweep (tag={self.tag!r}) has {len(tasks)} tasks — tasks with "
                    f"matching hashes will be silently skipped (INSERT OR IGNORE).\n"
                    f"  If this is a different sweep reusing the same save_dir, "
                    f"consider using a per-sweep subdirectory to avoid DB collisions."
                )

        queue_tasks(self.db_path, tasks, tag=self.tag)
        logger.info(f"Queued {len(tasks)} tasks (tag={self.tag!r})")

        # ----- backend -----
        self.job = None  # set in run() once an HPC job is submitted
        self.backend = None
        if slurm_config:
            p = OmegaConf.to_container(OmegaConf.load(slurm_config), resolve=True)
            if after:
                p["after"] = after
            self.backend = SlurmBackend(folder=self.save_dir / "slurm_logs", **p)
        elif pbs_config:
            p = OmegaConf.to_container(OmegaConf.load(pbs_config), resolve=True)
            if after:
                p["after"] = after
            self.backend = PBSBackend(folder=self.save_dir / "pbs_logs", **p)

    def _run_locally(self):
        num_workers = self.local_workers or self.n_jobs
        if num_workers == 1 and not self.isolated:
            try:
                worker_loop(self.func, self.cfg, self.task_target, self.db_path,
                            tags=[self.tag])
            except WorkerExecutionError:
                # The controller returns typed results from the persisted DB;
                # standalone/scheduler workers let this exception exit nonzero.
                pass
        else:
            # Use 'spawn' instead of the default 'fork' to avoid inheriting
            # GPU/CUDA contexts and threading locks from the parent process.
            # fork + CUDA (or any initialised GPU library) causes deadlocks
            # in child processes.
            ctx = multiprocessing.get_context("spawn")
            procs = [
                ctx.Process(
                    target=worker_loop,
                    args=(self.func, self.cfg, self.task_target, self.db_path,
                          [self.tag]),
                )
                for _ in range(num_workers)
            ]
            for p in procs:
                p.start()
            try:
                for p in procs:
                    p.join()
            except KeyboardInterrupt:
                from .taskdb import mark_orphans_interrupted

                logger.warning(
                    "Keyboard interrupt — terminating worker processes. "
                    "In-flight tasks will be marked interrupted."
                )
                for p in procs:
                    p.terminate()
                for p in procs:
                    p.join(timeout=10)
                # Force-kill any that didn't exit cleanly.
                for p in procs:
                    if p.is_alive():
                        p.kill()
                        p.join()
                # Workers killed via SIGTERM don't run their own interrupt
                # handler, so reconcile here: any task still 'running' is
                # owned by a now-dead worker.
                mark_orphans_interrupted(self.db_path, tags=[self.tag])
                raise

    def _wait_for_completion(
        self, timeout: int = None, poll_interval: int = None
    ) -> bool:
        """
        Wait for all tasks to complete by polling the database.

        Args:
            timeout: Maximum time to wait in seconds (None = no timeout)
            poll_interval: How often to check status in seconds (defaults to config.POLL_INTERVAL)

        Returns:
            bool: True if all tasks completed successfully, False on timeout or failure
        """
        if poll_interval is None:
            poll_interval = config.POLL_INTERVAL
        import time
        from .taskdb import get_status_counts, mark_orphans_interrupted

        logger.info("Waiting for tasks to complete...")
        start_time = time.time()
        last_log_time = start_time

        job_id = self.job.job_id if self.job is not None else None
        # Require the job to look terminal on this many consecutive polls
        # before reconciling, so a single racy/transient status read (e.g.
        # squeue+sacct both momentarily blank right after submission, or a
        # qstat hiccup) can never reap a healthy job.
        terminal_confirmations = 0
        TERMINAL_DEBOUNCE = 3

        try:
            while True:
                status_counts = get_status_counts(self.db_path, tags=[self.tag])
                pending = status_counts.get("pending", 0)
                running = status_counts.get("running", 0)
                done = status_counts.get("done", 0)
                failed = status_counts.get("failed", 0)
                interrupted = status_counts.get("interrupted", 0)
                total = pending + running + done + failed + interrupted

                # All terminal — nothing left in flight.
                if pending == 0 and running == 0:
                    issues = failed + interrupted
                    if issues:
                        logger.warning(
                            f"Sweep finished with issues: {failed} failed, {interrupted} interrupted"
                        )
                    else:
                        logger.success(f"All {done} tasks completed successfully")
                    return issues == 0

                # Reconcile against the scheduler's ground truth: only when the
                # job is *confirmed* ended (not merely 'unknown'/unreported) yet
                # tasks remain pending/running did the worker die (wall-time,
                # OOM, crash) without finishing them. Debounced to ignore
                # transient status reads.
                if job_id is not None and self.backend is not None:
                    if self.backend.is_terminal(job_id):
                        terminal_confirmations += 1
                    else:
                        terminal_confirmations = 0

                    if terminal_confirmations >= TERMINAL_DEBOUNCE:
                        orphaned = mark_orphans_interrupted(
                            self.db_path, job_id=job_id, tags=[self.tag]
                        )
                        logger.warning(
                            f"HPC job {job_id} has ended but "
                            f"{pending} task(s) pending / {running} running. "
                            f"Marked {orphaned} orphaned task(s) interrupted. "
                            f"Re-run pending/interrupted tasks with: "
                            f"flexlock-worker --task-db {self.db_path} --reclaim"
                        )
                        return False

                # Log progress periodically
                elapsed = time.time() - start_time
                if elapsed - (last_log_time - start_time) >= config.LOG_FREQUENCY:
                    progress = (done + failed + interrupted) / total * 100 if total > 0 else 0
                    logger.info(
                        f"Progress: {progress:.1f}% "
                        f"(pending={pending}, running={running}, done={done}, "
                        f"failed={failed}, interrupted={interrupted})"
                    )
                    last_log_time = time.time()

                # Check timeout
                if timeout and elapsed > timeout:
                    logger.warning(
                        f"Timeout after {timeout}s "
                        f"(pending={pending}, running={running})"
                    )
                    return False

                time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.warning(
                "Keyboard interrupt received while waiting. "
                "The submitted job keeps running on the cluster; "
                f"monitor with: flexlock-status {self.db_path}"
            )
            return False

    def run(self, wait: bool = True, timeout: int = None, poll_interval: int = None):
        """
        Execute tasks via backend or locally.

        Args:
            wait: If True, blocks until all tasks complete (default: True for local, optional for HPC)
            timeout: Maximum time to wait in seconds (None = no timeout, applies only if wait=True)
            poll_interval: How often to check task status in seconds (defaults to config.POLL_INTERVAL, applies only if wait=True)

        Returns:
            bool: True if tasks completed successfully (or not waiting), False on timeout/failure
        """
        from flexlock.taskdb import dump_to_yaml
        from flexlock.record import list_task_records
        from flexlock.outputs import validate_outputs
        from flexlock.utils import merge_task_into_cfg

        # Already-done DB rows are reused without being claimed by a worker.
        # Validate their resolved receipts before taking that shortcut.
        for row in list_task_records(self.db_path, tags=[self.tag]):
            if row['status'] != 'done':
                continue
            receipt = row.get("snapshot") or {}
            if "stages" in receipt:
                stages = list(receipt["stages"].values())
            elif "config" in receipt:
                stages = [receipt]
            elif "_stages_" in row["task"]:
                stages = [{'config': s} for s in row["task"]["_stages_"]]
            else:
                stages = [{'config': merge_task_into_cfg(self.cfg, row["task"], self.task_target)}]
            for stage in stages:
                validate_outputs(OmegaConf.create(stage['config']), record_dir=stage.get('record_dir'))

        if pending_count(self.db_path, tags=[self.tag]) == 0:
            logger.info("All tasks already completed.")
            dump_to_yaml(self.db_path, self.save_dir / "run.lock.tasks",
                         tags=[self.tag])
            from flexlock.taskdb import get_status_counts

            counts = get_status_counts(self.db_path, tags=[self.tag])
            return not any(counts.get(s, 0) for s in ("failed", "interrupted", "running"))

        # 1. Prepare Root Directory
        root_dir = Path(self.cfg.save_dir)  # e.g., outputs/sweep_name
        root_dir.mkdir(parents=True, exist_ok=True)

        # 2. CREATE MASTER SNAPSHOT
        # This captures the Code state ONCE for the whole sweep
        # We assume the Main Process has the correct context (repos, etc.)
        _, data, _ = extract_tracking_info(self.cfg)
        # Include repos of the tasks' own _target_s: when the base config has
        # none (single HPC run, --sweep-file of full configs), workers would
        # otherwise record no code state (they snapshot tasks as deltas).
        repos = collect_task_repos(self.cfg, self.tasks, self.task_target)
        snapshot(
            self.cfg, repos=repos, data=data, save_path=root_dir, note=self.note,
            meta={"task_record": self.task_record, "shared_save_dirs": self.shared_save_dirs},
        )

        # 3. Populate SQLite DB
        # Store 'root_dir' in the DB so workers know where the Master Lock is.
        # This is handled by the existing queue_tasks call in __init__

        try:
            logger.info(
                f"Use 'flexlock-status {self.db_path}' to monitor task progress"
            )

            if self.backend is None:
                # Local execution - always completes synchronously
                logger.info("Running locally (pull-from-DB)")
                self._run_locally()

                # All local workers have exited. Any task still 'running' was
                # owned by a worker that died (hard crash / OOM) without
                # recording a terminal state — reconcile it now.
                from .taskdb import get_status_counts, mark_orphans_interrupted

                orphaned = mark_orphans_interrupted(self.db_path, tags=[self.tag])
                if orphaned:
                    logger.warning(
                        f"Marked {orphaned} task(s) interrupted "
                        f"(worker exited without finishing them)."
                    )

                status_counts = get_status_counts(self.db_path, tags=[self.tag])
                failed = status_counts.get("failed", 0)
                interrupted = status_counts.get("interrupted", 0)
                success = (failed + interrupted) == 0
            else:
                # HPC backend execution
                # Fixed args for worker_loop (as tuple for *args)
                fixed_args = (self.func, self.cfg, self.task_target, self.db_path,
                              [self.tag])
                self.job = self.backend.submit(worker_loop, *fixed_args)
                logger.info(
                    f"Submitted {self.backend.__class__.__name__} job {self.job.job_id}"
                )

                # Wait for completion if requested
                if wait:
                    success = self._wait_for_completion(timeout, poll_interval)
                else:
                    logger.info("Job submitted (not waiting for completion)")
                    success = True

        finally:
            # Dump tasks to YAML after all jobs are submitted (or completed locally)
            dump_to_yaml(self.db_path, self.save_dir / "run.lock.tasks",
                         tags=[self.tag])

        return success
