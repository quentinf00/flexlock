"""Export utilities for FlexLock - extract snapshots from database to files."""

import argparse
import sys
import json
import yaml
import tempfile
import os
from pathlib import Path
from loguru import logger
from flexlock.taskdb import get_task_snapshot, list_task_snapshots


def export_task(db_path: Path, task_id: str, output_dir: Path) -> None:
    """
    Export a single task snapshot from database to a standalone directory.

    Args:
        db_path: Path to SQLite database
        task_id: Hash of the task to export
        output_dir: Directory to write the exported snapshot

    Raises:
        ValueError: If task not found in database
    """
    snapshot_data = get_task_snapshot(db_path, task_id)
    if not snapshot_data:
        raise ValueError(f"Task {task_id} not found in {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Atomic write of run.lock file
    with tempfile.NamedTemporaryFile("w", dir=output_dir, delete=False) as tf:
        yaml.dump(snapshot_data, tf, sort_keys=False)
        tmp_name = tf.name
    os.replace(tmp_name, output_dir / "run.lock")

    logger.info(f"Exported task {task_id} to {output_dir}")


def export_all_tasks(db_path: Path, output_base_dir: Path, status: str = None) -> None:
    """
    Export all tasks (or filtered by status) from database to separate directories.

    Args:
        db_path: Path to SQLite database
        output_base_dir: Base directory for exports (each task gets a subdirectory)
        status: Optional filter by status (pending, running, done, failed)
    """
    tasks = list_task_snapshots(db_path, status)

    if not tasks:
        logger.warning(
            f"No tasks found in {db_path}"
            + (f" with status={status}" if status else "")
        )
        return

    output_base_dir.mkdir(parents=True, exist_ok=True)

    for task_id, snapshot_data, task_status in tasks:
        if snapshot_data:
            task_output_dir = output_base_dir / f"task_{task_id[:8]}"
            task_output_dir.mkdir(parents=True, exist_ok=True)

            # Atomic write
            with tempfile.NamedTemporaryFile(
                "w", dir=task_output_dir, delete=False
            ) as tf:
                yaml.dump(snapshot_data, tf, sort_keys=False)
                tmp_name = tf.name
            os.replace(tmp_name, task_output_dir / "run.lock")

            logger.info(
                f"Exported task {task_id[:8]} (status={task_status}) to {task_output_dir}"
            )

    logger.info(f"Exported {len(tasks)} tasks to {output_base_dir}")


def main():
    """CLI entry point for flexlock export command."""
    parser = argparse.ArgumentParser(
        description="Export FlexLock task snapshots from database to files"
    )

    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to tasks database (e.g., outputs/sweep/tasks.db)",
    )

    parser.add_argument(
        "--task", help="Task ID to export (hash). If not specified, exports all tasks."
    )

    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for exported snapshot(s)",
    )

    parser.add_argument(
        "--status",
        choices=["pending", "running", "done", "failed"],
        help="Filter tasks by status (only used when exporting all tasks)",
    )

    args = parser.parse_args()

    # Validate database exists
    if not args.db.exists():
        logger.error(f"Database not found: {args.db}")
        sys.exit(1)

    try:
        if args.task:
            # Export single task
            export_task(args.db, args.task, args.out)
        else:
            # Export all tasks
            export_all_tasks(args.db, args.out, args.status)

        logger.success("Export completed successfully")

    except Exception as e:
        logger.error(f"Export failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
