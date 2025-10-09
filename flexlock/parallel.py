"""
This module contains the advanced parallel execution logic for FlexLock.
It supports a multi-level parallelism hierarchy:
1. Slurm Job Arrays (via submitit's map_array)
2. Task distribution within a Slurm job (across nodes/tasks)
3. Local parallel execution using joblib for a given task subset.
It also supports checkpointing of individual tasks to avoid re-computation.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Callable, List

import yaml
from joblib import Parallel, delayed
from omegaconf import DictConfig, OmegaConf

log = logging.getLogger(__name__)

try:
    import submitit
except ImportError:
    submitit = None


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


def merge_task_into_cfg(cfg: DictConfig, task: Any, task_to: str) -> DictConfig:
    """Merge a task into the config."""
    # Create a minimal config with just the task structure

    task_branch = OmegaConf.create({})
    OmegaConf.update(task_branch, task_to, task, force_add=True)
    print(cfg, task, task_branch)
    return OmegaConf.merge(cfg, task_branch)


class ParallelExecutor:
    """A class to handle multi-level parallel execution of a function."""

    def __init__(self,
                 func: Callable,
                 tasks: List[Any],
                 task_to: str,
                 cfg: DictConfig,
                 n_jobs: int,
                 slurm_config: str):
        self.func = func
        self.initial_tasks = tasks
        self.task_to = task_to
        self.cfg = cfg
        self.n_jobs = n_jobs
        self.slurm_config_path = slurm_config
        self.undone_tasks = []

        if not self.cfg.get('save_dir'):
            raise ValueError("Configuration must contain a 'save_dir' for parallel execution tracking.")
        self.done_dir = Path(self.cfg.save_dir) / ".flexlock_done"
        self.done_dir.mkdir(parents=True, exist_ok=True)

    def _get_task_id(self, task: Any) -> str:
        """Create a unique and filesystem-safe ID for a task."""
        task_str = str(task)
        return hashlib.sha1(task_str.encode()).hexdigest()

    def _get_done_file_path(self, task: Any) -> Path:
        """Get the path to the 'done' file for a given task."""
        return self.done_dir / f"{self._get_task_id(task)}.done"

    def _filter_done_tasks(self):
        """Filters the initial task list to exclude tasks that are already done."""
        self.undone_tasks = [
            task for task in self.initial_tasks
            if not self._get_done_file_path(task).exists()
        ]
        total_count = len(self.initial_tasks)
        done_count = total_count - len(self.undone_tasks)
        log.info(f"Task status: {total_count} total, {done_count} already complete, {len(self.undone_tasks)} to run.")

    def run_single(self, task: Any):
        """Run the function for a single task and mark it as done on success."""
        done_file = self._get_done_file_path(task)
        try:
            task_cfg = merge_task_into_cfg(self.cfg, task, self.task_to)
            log.debug(f"Running task with config:\n{OmegaConf.to_yaml(task_cfg)}")
            self.func(task_cfg)
            # Create done file on success
            done_file.touch()
            log.info(f"Task {self._get_task_id(task)} completed successfully.")
        except Exception as e:
            log.error(f"Task {self._get_task_id(task)} failed: {e}", exc_info=True)
            # Optionally remove a partially created done file if that's desired
            if done_file.exists():
                os.remove(done_file)
            raise

    def _run_subset_locally(self, tasks_subset: List[Any]):
        """Executes a subset of tasks, either serially or with joblib."""
        if not tasks_subset:
            return

        log.info(f"Processing a subset of {len(tasks_subset)} tasks with n_jobs={self.n_jobs}.")
        if self.n_jobs > 1:
            Parallel(n_jobs=self.n_jobs)(
                delayed(self.run_single)(task) for task in tasks_subset
            )
        else:
            for task in tasks_subset:
                self.run_single(task)

    def _distribute_and_run(self, tasks_to_distribute: List[Any]):
        """
        Function executed by a Slurm worker. It determines its rank and world
        size to select its share of tasks and then runs them.
        """
        env = submitit.JobEnvironment()
        my_tasks = tasks_to_distribute[env.global_rank::env.world_size]
        log.info(
            f"Slurm worker {env.global_rank}/{env.world_size} received {len(my_tasks)} tasks."
        )
        self._run_subset_locally(my_tasks)

    def run(self):
        """
        Main entry point for execution.
        Filters completed tasks and then delegates to the appropriate
        execution mode (local or Slurm).
        """
        self._filter_done_tasks()
        if not self.undone_tasks:
            log.info("All tasks are already complete. Nothing to do.")
            return

        if self.slurm_config_path:
            if submitit is None:
                raise ImportError("The 'submitit' library is required for Slurm execution.")

            log.info(f"Using Slurm config: {self.slurm_config_path}")
            slurm_kwargs = OmegaConf.to_container(
                OmegaConf.load(self.slurm_config_path), resolve=True
            )
            array_parallelism = slurm_kwargs.pop("slurm_array_parallelism", 1)

            executor = submitit.AutoExecutor(folder="submitit_logs")
            executor.update_parameters(**slurm_kwargs)

            if array_parallelism > 1:
                log.info(f"Distributing tasks across a Slurm job array of size {array_parallelism}.")
                # Split tasks into chunks for the job array
                tasks_per_job = -(-len(self.undone_tasks) // array_parallelism)  # Ceiling division
                task_chunks = [
                    self.undone_tasks[i:i + tasks_per_job]
                    for i in range(0, len(self.undone_tasks), tasks_per_job)
                ]
                jobs = executor.map_array(self._distribute_and_run, task_chunks)
                log.info(f"Submitted job array with {len(jobs)} jobs.")
            else:
                log.info("Submitting a single Slurm job.")
                job = executor.submit(self._distribute_and_run, self.undone_tasks)
                log.info(f"Submitted single job {job.job_id}")
        else:
            log.info("Running all tasks locally.")
            self._run_subset_locally(self.undone_tasks)

    def checkpoint(self):
        """
        Checkpoint the execution. On requeue, this will call self.run() again,
        which will automatically filter out completed tasks.
        """
        log.info("Checkpointing...")
        return submitit.helpers.DelayedSubmission(self.run)
