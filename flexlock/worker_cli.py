"""CLI entry point for attaching extra workers to an existing task DB."""

import argparse
import multiprocessing
import sys
from pathlib import Path

from loguru import logger
from omegaconf import OmegaConf


def main():
    parser = argparse.ArgumentParser(
        description="Attach one or more workers to an existing FlexLock task DB."
    )
    parser.add_argument(
        "--task-db",
        required=True,
        metavar="FILE",
        help="Path to the .tasks.db file created by a previous flexlock-run sweep.",
    )
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel worker processes to spawn locally (default: 1). "
             "Ignored when --slurm-config or --pbs-config is used.",
    )

    backend_group = parser.add_mutually_exclusive_group()
    backend_group.add_argument(
        "--slurm-config",
        metavar="FILE",
        help="Submit workers as a Slurm job using this YAML config.",
    )
    backend_group.add_argument(
        "--pbs-config",
        metavar="FILE",
        help="Submit workers as a PBS job using this YAML config.",
    )

    args = parser.parse_args()

    db_path = Path(args.task_db)
    if not db_path.exists():
        logger.error(f"Task DB not found: {db_path}")
        sys.exit(1)

    from flexlock.taskdb import pending_count
    from flexlock.worker import worker_loop

    n_pending = pending_count(db_path)
    if n_pending == 0:
        logger.info("No pending tasks in DB — nothing to do.")
        return

    # Tasks stored in the DB are complete configs; pass an empty base cfg and
    # no task_to so worker_loop uses each task dict as-is.
    empty_cfg = OmegaConf.create({})

    if args.slurm_config or args.pbs_config:
        logs_dir = db_path.parent / ("slurm_logs" if args.slurm_config else "pbs_logs")
        if args.slurm_config:
            from flexlock.backends.slurm import SlurmBackend
            params = OmegaConf.to_container(OmegaConf.load(args.slurm_config), resolve=True)
            backend = SlurmBackend(folder=logs_dir, **params)
        else:
            from flexlock.backends.pbs import PBSBackend
            params = OmegaConf.to_container(OmegaConf.load(args.pbs_config), resolve=True)
            backend = PBSBackend(folder=logs_dir, **params)

        logger.info(f"Submitting {backend.__class__.__name__} worker job for {db_path} ({n_pending} pending tasks)")
        job = backend.submit(worker_loop, None, empty_cfg, None, db_path)
        logger.info(f"Submitted job {job.job_id}")
    else:
        logger.info(f"Attaching {args.n_jobs} local worker(s) to {db_path} ({n_pending} pending tasks)")
        if args.n_jobs == 1:
            worker_loop(None, empty_cfg, None, db_path)
        else:
            ctx = multiprocessing.get_context("spawn")
            procs = [
                ctx.Process(target=worker_loop, args=(None, empty_cfg, None, db_path))
                for _ in range(args.n_jobs)
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join()


if __name__ == "__main__":
    main()
