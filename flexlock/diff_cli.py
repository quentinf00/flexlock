"""CLI for comparing FlexLock snapshots from various sources."""

import argparse
import sys
import yaml
from pathlib import Path
from loguru import logger
from flexlock.diff import RunDiff
from flexlock.taskdb import get_task_snapshot


def load_snapshot_from_dir(dir_path: Path) -> dict:
    """Load snapshot from a directory (finds run.lock file)."""
    lock_file = dir_path / "run.lock"
    if not lock_file.exists():
        raise FileNotFoundError(f"No run.lock found in {dir_path}")

    with open(lock_file) as f:
        return yaml.safe_load(f)


def load_snapshot_from_db(db_path: Path, task_id: str) -> dict:
    """Load snapshot from database by task_id."""
    snapshot = get_task_snapshot(db_path, task_id)
    if snapshot is None:
        raise ValueError(f"No snapshot found for task_id '{task_id}' in {db_path}")
    return snapshot


def compare_snapshots(snap1: dict, snap2: dict, show_details: bool = False) -> bool:
    """
    Compare two snapshots and print results.

    Args:
        snap1: First snapshot dictionary
        snap2: Second snapshot dictionary
        show_details: If True, show detailed differences

    Returns:
        bool: True if snapshots match, False otherwise
    """
    diff = RunDiff(snap1, snap2)

    print("\n=== Snapshot Comparison ===\n")

    # Git comparison
    git_match = diff.compare_git()
    print(f"Git:    {'✓ Match' if git_match else '✗ Differ'}")
    if not git_match and show_details:
        for d in diff.diffs.get("git", []):
            print(f"  - {d}")

    # Config comparison
    config_match = diff.compare_config()
    print(f"Config: {'✓ Match' if config_match else '✗ Differ'}")
    if not config_match and show_details:
        for d in diff.diffs.get("config", []):
            print(f"  - {d}")

    # Data comparison
    data_match = diff.compare_data()
    print(f"Data:   {'✓ Match' if data_match else '✗ Differ'}")
    if not data_match and show_details:
        for d in diff.diffs.get("data", []):
            print(f"  - {d}")

    # Overall
    is_match = diff.is_match()
    print(f"\nOverall: {'✓ Snapshots Match' if is_match else '✗ Snapshots Differ'}\n")

    return is_match


def main():
    """CLI entry point for flexlock diff command."""
    parser = argparse.ArgumentParser(
        description="Compare FlexLock snapshots from various sources"
    )

    # Create subcommands for different comparison modes
    subparsers = parser.add_subparsers(
        dest="mode", required=True, help="Comparison mode"
    )

    # Mode 1: Compare two directories (traditional)
    dir_parser = subparsers.add_parser(
        "dirs", help="Compare two directory-based snapshots"
    )
    dir_parser.add_argument("dir1", type=Path, help="First directory")
    dir_parser.add_argument("dir2", type=Path, help="Second directory")
    dir_parser.add_argument(
        "--details", action="store_true", help="Show detailed differences"
    )

    # Mode 2: Compare two tasks in DB
    db_parser = subparsers.add_parser("db", help="Compare two DB-based snapshots")
    db_parser.add_argument("db_path", type=Path, help="Path to tasks database")
    db_parser.add_argument("task_id1", help="First task ID (hash)")
    db_parser.add_argument("task_id2", help="Second task ID (hash)")
    db_parser.add_argument(
        "--details", action="store_true", help="Show detailed differences"
    )

    # Mode 3: Compare directory to DB task
    mixed_parser = subparsers.add_parser(
        "mixed", help="Compare directory snapshot to DB snapshot"
    )
    mixed_parser.add_argument("dir_path", type=Path, help="Directory path")
    mixed_parser.add_argument("db_path", type=Path, help="Database path")
    mixed_parser.add_argument("task_id", help="Task ID in database")
    mixed_parser.add_argument(
        "--details", action="store_true", help="Show detailed differences"
    )

    args = parser.parse_args()

    try:
        if args.mode == "dirs":
            # Validate directories exist
            if not args.dir1.exists():
                logger.error(f"Directory not found: {args.dir1}")
                sys.exit(1)
            if not args.dir2.exists():
                logger.error(f"Directory not found: {args.dir2}")
                sys.exit(1)

            snap1 = load_snapshot_from_dir(args.dir1)
            snap2 = load_snapshot_from_dir(args.dir2)
            is_match = compare_snapshots(snap1, snap2, args.details)

        elif args.mode == "db":
            # Validate database exists
            if not args.db_path.exists():
                logger.error(f"Database not found: {args.db_path}")
                sys.exit(1)

            snap1 = load_snapshot_from_db(args.db_path, args.task_id1)
            snap2 = load_snapshot_from_db(args.db_path, args.task_id2)
            is_match = compare_snapshots(snap1, snap2, args.details)

        elif args.mode == "mixed":
            # Validate paths exist
            if not args.dir_path.exists():
                logger.error(f"Directory not found: {args.dir_path}")
                sys.exit(1)
            if not args.db_path.exists():
                logger.error(f"Database not found: {args.db_path}")
                sys.exit(1)

            snap1 = load_snapshot_from_dir(args.dir_path)
            snap2 = load_snapshot_from_db(args.db_path, args.task_id)
            is_match = compare_snapshots(snap1, snap2, args.details)

        # Exit with appropriate code
        sys.exit(0)

    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
