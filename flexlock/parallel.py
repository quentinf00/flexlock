"""Manages parallel task execution for FlexLock."""

from pathlib import Path
from omegaconf import OmegaConf, DictConfig
from loguru import logger
from flexlock.taskdb import queue_tasks, pending_count
from flexlock.worker import worker_loop
from flexlock.backends.slurm import SlurmBackend
from flexlock.backends.pbs import PBSBackend
from multiprocessing import Process
import yaml
from typing import Any, List
from flexlock.snapshot import snapshot
from flexlock.utils import extract_tracking_info
from flexlock import config


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
    ):
        """Initializes the ParallelExecutor.

        Args:
            func: The function to execute for each task.
            tasks: A list of tasks to be executed.
            task_target: The OmegaConf path to merge task-specific configurations into.
            cfg: The base OmegaConf configuration.
            n_jobs: Number of parallel jobs for local execution.
            slurm_config: Path to the Slurm configuration file.
            pbs_config: Path to the PBS configuration file.
            local_workers: Number of local worker processes to spawn.
        """
        self.func = func
        self.tasks = tasks
        self.task_target = task_target
        self.cfg = cfg
        self.n_jobs = n_jobs
        self.local_workers = local_workers

        self.save_dir = Path(cfg.save_dir)
        self.db_path = self.save_dir / "run.lock.tasks.db"

        queue_tasks(self.db_path, tasks)
        logger.info(f"Queued {len(tasks)} tasks")

        # ----- backend -----
        self.backend = None
        if slurm_config:
            p = OmegaConf.to_container(OmegaConf.load(slurm_config), resolve=True)
            self.backend = SlurmBackend(folder=self.save_dir / "slurm_logs", **p)
        elif pbs_config:
            p = OmegaConf.to_container(OmegaConf.load(pbs_config), resolve=True)
            self.backend = PBSBackend(folder=self.save_dir / "pbs_logs", **p)

    def _run_locally(self):
        num_workers = self.local_workers or self.n_jobs 
        if num_workers == 1:
            worker_loop(self.func, self.cfg, self.task_target, self.db_path)
        else:
            procs = [
                Process(
                    target=worker_loop,
                    args=(self.func, self.cfg, self.task_target, self.db_path),
                )
                for _ in range(num_workers)
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join()

    def _wait_for_completion(self, timeout: int = None, poll_interval: int = None) -> bool:
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
        from .taskdb import get_status_counts

        logger.info("Waiting for tasks to complete...")
        start_time = time.time()
        last_log_time = start_time

        try:
            while True:
                # Get current status
                status_counts = get_status_counts(self.db_path)
                pending = status_counts.get('pending', 0)
                running = status_counts.get('running', 0)
                done = status_counts.get('done', 0)
                failed = status_counts.get('failed', 0)
                total = pending + running + done + failed

                # Check if complete
                if pending == 0 and running == 0:
                    if failed > 0:
                        logger.warning(f"All tasks completed with {failed} failures")
                    else:
                        logger.success(f"All {done} tasks completed successfully")
                    return failed == 0

                # Log progress periodically
                elapsed = time.time() - start_time
                if elapsed - (last_log_time - start_time) >= config.LOG_FREQUENCY:
                    progress = (done + failed) / total * 100 if total > 0 else 0
                    logger.info(
                        f"Progress: {progress:.1f}% "
                        f"(pending: {pending}, running: {running}, done: {done}, failed: {failed})"
                    )
                    last_log_time = time.time()

                # Check timeout
                if timeout and elapsed > timeout:
                    logger.warning(f"Timeout after {timeout}s (pending: {pending}, running: {running})")
                    return False

                # Wait before next check
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.warning(
                "Keyboard interrupt received. "
                "Tasks are still running. "
                f"Check status with: flexlock-status {self.db_path}"
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

        if pending_count(self.db_path) == 0:
            logger.info("All tasks already completed.")
            dump_to_yaml(self.db_path, self.save_dir / "run.lock.tasks")
            return True

        # 1. Prepare Root Directory
        root_dir = Path(self.cfg.save_dir) # e.g., outputs/sweep_name
        root_dir.mkdir(parents=True, exist_ok=True)

        # 2. CREATE MASTER SNAPSHOT
        # This captures the Code state ONCE for the whole sweep
        # We assume the Main Process has the correct context (repos, etc.)
        repos, data, _ = extract_tracking_info(self.cfg)
        # Set default repos if none specified
        if not repos:
            repos = {"main": "."}
        snapshot(
            self.cfg,
            repos=repos,
            data=data,
            save_path=root_dir
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

                # Check if any tasks failed
                from .taskdb import get_status_counts
                status_counts = get_status_counts(self.db_path)
                failed = status_counts.get('failed', 0)
                success = failed == 0
            else:
                # HPC backend execution
                # Fixed args for worker_loop (as tuple for *args)
                fixed_args = (self.func, self.cfg, self.task_target, self.db_path)
                job = self.backend.submit(worker_loop, *fixed_args)
                logger.info(
                    f"Submitted {self.backend.__class__.__name__} job {job.job_id}"
                )

                # Wait for completion if requested
                if wait:
                    success = self._wait_for_completion(timeout, poll_interval)
                else:
                    logger.info("Job submitted (not waiting for completion)")
                    success = True

        finally:
            # Dump tasks to YAML after all jobs are submitted (or completed locally)
            dump_to_yaml(self.db_path, self.save_dir / "run.lock.tasks")

        return success
