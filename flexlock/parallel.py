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

    def _extract_tracking_info(self, cfg):
        """
        Extract tracking info from config for master snapshot.
        """
        repos = {"main": "."}  # Default
        data = {}
        
        # Check if the config has tracking instructions
        if "_snapshot_" in cfg:
            snap_cfg = cfg._snapshot_
            
            if "repos" in snap_cfg:
                repos.update(OmegaConf.to_container(snap_cfg.repos, resolve=True))
            
            if "data" in snap_cfg:
                data.update(OmegaConf.to_container(snap_cfg.data, resolve=True))

        return repos, data

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

    def run(self):
        from flexlock.taskdb import dump_to_yaml  # Import dump_to_yaml here

        if pending_count(self.db_path) == 0:
            logger.info("All tasks already completed.")
            dump_to_yaml(self.db_path, self.save_dir / "run.lock.tasks")
            return
        
        # 1. Prepare Root Directory
        root_dir = Path(self.cfg.save_dir) # e.g., outputs/sweep_name
        root_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. CREATE MASTER SNAPSHOT
        # This captures the Code state ONCE for the whole sweep
        # We assume the Main Process has the correct context (repos, etc.)
        repos, data = self._extract_tracking_info(self.cfg)
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
                f"""Use the following command to display job status: 
                
                sqlite3  {self.db_path} 'SELECT status, count(*) as count, MIN(ts_start) as first_start, MAX(ts_end) as last_end  FROM tasks group by status; -header -box'
                
                """
            )
            if self.backend is None:
                logger.info("Running locally (pull-from-DB)")
                self._run_locally()
            else:
                # Fixed args for worker_loop (as tuple for *args)
                fixed_args = (self.func, self.cfg, self.task_target, self.db_path)
                job = self.backend.submit(worker_loop, *fixed_args)
                logger.info(
                    f"Submitted {self.backend.__class__.__name__} job {job.job_id}"
                )
                # TODO: Add a mechanism to wait for single job to complete
        finally:
            # Dump tasks to YAML after all jobs are submitted (or completed locally)
            dump_to_yaml(self.db_path, self.save_dir / "run.lock.tasks")
