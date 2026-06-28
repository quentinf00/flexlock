"""CLI entry point for attaching extra workers to an existing task DB."""

import argparse
import multiprocessing
import sys
from pathlib import Path

from loguru import logger
from omegaconf import OmegaConf


def main():
    parser = argparse.ArgumentParser(
        description="Attach one or more workers to an existing FlexLock task DB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Attach 4 local workers to an existing DB
  flexlock-worker --task-db outputs/run/run.lock.tasks.db --n-jobs 4

  # Only process tasks tagged "extract"
  flexlock-worker --task-db outputs/run/run.lock.tasks.db --tags extract --n-jobs 4

  # Reclaim stranded tasks for tag "collocate" then re-run them
  flexlock-worker --task-db outputs/run/run.lock.tasks.db --tags collocate --reclaim
        """,
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
    parser.add_argument(
        "--tags",
        metavar="TAG[,TAG...]",
        help="Comma-separated list of tags to process. Workers will only claim "
             "tasks whose tag matches. Omit to process all tasks (including "
             "legacy untagged rows).",
    )
    parser.add_argument(
        "--reclaim",
        action="store_true",
        help="Before starting, reset tasks stranded in 'running' (by a worker "
             "that died without cleanup) back to 'pending' so they re-run. "
             "Scoped to --tags when provided.",
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

    # Parse --tags into a list (None when omitted).
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None

    from flexlock.taskdb import pending_count, reclaim_running
    from flexlock.worker import worker_loop

    if args.reclaim:
        reclaimed = reclaim_running(db_path, tags=tags)
        logger.info(f"Reclaimed {reclaimed} stranded 'running' task(s) → pending"
                    + (f" (tags={tags})" if tags else ""))

    n_pending = pending_count(db_path, tags=tags)
    if n_pending == 0:
        logger.info("No pending tasks in DB — nothing to do."
                    + (f" (tags={tags})" if tags else ""))
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

        logger.info(
            f"Submitting {backend.__class__.__name__} worker job for {db_path} "
            f"({n_pending} pending tasks"
            + (f", tags={tags}" if tags else "")
            + ")"
        )
        job = backend.submit(worker_loop, None, empty_cfg, None, db_path, tags)
        logger.info(f"Submitted job {job.job_id}")
    else:
        logger.info(
            f"Attaching {args.n_jobs} local worker(s) to {db_path} "
            f"({n_pending} pending tasks"
            + (f", tags={tags}" if tags else "")
            + ")"
        )
        if args.n_jobs == 1:
            worker_loop(None, empty_cfg, None, db_path, tags)
        else:
            ctx = multiprocessing.get_context("spawn")
            procs = [
                ctx.Process(target=worker_loop, args=(None, empty_cfg, None, db_path, tags))
                for _ in range(args.n_jobs)
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join()


if __name__ == "__main__":
    main()
