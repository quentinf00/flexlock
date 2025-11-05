# flexlock/parallel.py
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


def load_tasks(tasks: str, tasks_key: str, cfg: DictConfig) -> List[Any]:
    """Load tasks from a file or from the config."""
    if tasks:
        p_tasks = Path(tasks)
        if not p_tasks.exists():
            raise FileNotFoundError(f"Tasks file not found: {tasks}")
        if p_tasks.suffix == ".txt":
            return [line.strip() for line in p_tasks.read_text().splitlines()]
        elif p_tasks.suffix in [".yaml", ".yml"]:
            with p_tasks.open() as f:
                return yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported tasks file format: {p_tasks.suffix}")
    elif tasks_key:
        return OmegaConf.select(cfg, tasks_key)
    return []


class ParallelExecutor:
    def __init__(
        self,
        func,
        tasks,
        task_to: str,
        cfg: DictConfig,
        n_jobs: int = 1,
        slurm_config: str | None = None,
        pbs_config: str | None = None,
        local_workers: int | None = None,
    ):
        self.func = func
        self.tasks = tasks
        self.task_to = task_to
        self.cfg = cfg
        self.n_jobs = n_jobs
        self.local_workers = local_workers

        self.save_dir = Path(cfg.save_dir)
        self.db_path = self.save_dir / "run.lock.tasks.db"

        queue_tasks(self.db_path, tasks)
        logger.info(f"Queued {len(tasks)} tasks")

        # ----- backend -----
        self.backend = None
        self.array_size = 1
        if slurm_config:
            p = OmegaConf.to_container(OmegaConf.load(slurm_config), resolve=True)
            self.array_size = p.pop("array_parallelism", 1)
            self.backend = SlurmBackend(folder=self.save_dir / "slurm_logs", **p)
        elif pbs_config:
            p = OmegaConf.to_container(OmegaConf.load(pbs_config), resolve=True)
            self.array_size = p.pop("array_parallelism", 1)
            self.backend = PBSBackend(folder=self.save_dir / "pbs_logs", **p)

    def _run_locally(self):
        num_workers = self.local_workers or self.n_jobs or 1
        procs = [
            Process(
                target=worker_loop,
                args=(self.func, self.cfg, self.task_to, self.db_path)
            )
            for _ in range(num_workers)
        ]
        for p in procs: p.start()
        for p in procs: p.join()

    def run(self):
        from flexlock.taskdb import dump_to_yaml # Import dump_to_yaml here

        if pending_count(self.db_path) == 0:
            logger.info("All tasks already completed.")
            dump_to_yaml(self.db_path, self.save_dir / "run.lock.tasks")
            return
        try:
            if self.backend is None:
                logger.info("Running locally (pull-from-DB)")
                self._run_locally()
            else:
                # Fixed args for worker_loop (as tuple for *args)
                fixed_args = (self.func, self.cfg, self.task_to, self.db_path)

                if self.array_size > 1:
                    # Launch array_size identical workers
                    jobs = self.backend.map_array(worker_loop, [fixed_args] * self.array_size)
                    logger.info(f"Submitted {self.backend.__class__.__name__} array with {len(jobs)} sub-jobs")
                    # TODO: Add a mechanism to wait for array jobs to complete
                else:
                    job = self.backend.submit(worker_loop, *fixed_args)
                    logger.info(f"Submitted {self.backend.__class__.__name__} job {job.job_id}")
                    # TODO: Add a mechanism to wait for single job to complete
        finally:
            # Dump tasks to YAML after all jobs are submitted (or completed locally)
            dump_to_yaml(self.db_path, self.save_dir / "run.lock.tasks")

