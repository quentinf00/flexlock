"""CLI for comparing FlexLock snapshots from various sources.

Exit codes: ``0`` match, ``1`` differ, ``2`` error (so the command is usable
in scripts and CI — the old behaviour always exited 0).
"""

import argparse
import json
import sys
from pathlib import Path
from loguru import logger
from flexlock.diff import RunDiff
from flexlock.taskdb import get_task_snapshot


def load_snapshot_from_dir(dir_path: Path) -> dict:
    """Load a run's record (run.lock, or its task DB row for sweep tasks)."""
    from flexlock.record import load_record

    record = load_record(dir_path)
    if record is None:
        raise FileNotFoundError(f"No run record (run.lock or task marker) in {dir_path}")
    return record


def load_snapshot_from_db(db_path: Path, task_id: str) -> dict:
    """Load snapshot from database by task_id."""
    snapshot = get_task_snapshot(db_path, task_id)
    if snapshot is None:
        raise ValueError(f"No snapshot found for task_id '{task_id}' in {db_path}")
    return snapshot


def run_comparison(snap1: dict, snap2: dict) -> "tuple[bool, dict]":
    """Compare two snapshots, returning ``(is_match, diffs)``.

    The single source of truth for both the text/JSON printers here and
    ``flexlock why``. ``diffs`` is a JSON-serializable dict of lists keyed by
    ``git``/``config``/``data``/``env`` (only the categories that differ appear).
    """
    diff = RunDiff(snap1, snap2)
    # Run every comparison explicitly: is_match() short-circuits on the first
    # differing section, which would leave later sections out of diff.diffs.
    results = [
        diff.compare_git(),
        diff.compare_config(),
        diff.compare_data(),
        diff.compare_env(),
    ]
    return all(results), dict(diff.diffs)


def compare_snapshots(snap1: dict, snap2: dict, show_details: bool = False) -> bool:
    """Compare two snapshots and print a human-readable report."""
    is_match, diffs = run_comparison(snap1, snap2)

    print("\n=== Snapshot Comparison ===\n")
    for label, key in (("Git", "git"), ("Config", "config"), ("Data", "data"), ("Env", "env")):
        section_match = key not in diffs
        print(f"{label:6s}: {'✓ Match' if section_match else '✗ Differ'}")
        if not section_match and show_details:
            for d in diffs.get(key, []):
                print(f"  - {d}")

    for label, snap in (("first", snap1), ("second", snap2)):
        drift = snap.get("code_drift")
        if drift:
            files = ", ".join(f"{r}:{p}" for r, ps in drift.items() for p in ps)
            print(f"⚠ Code drift in {label} run (recorded tree may not match "
                  f"what ran): {files}")

    print(f"\nOverall: {'✓ Snapshots Match' if is_match else '✗ Snapshots Differ'}\n")
    return is_match


def main():
    """CLI entry point for flexlock diff command."""
    parser = argparse.ArgumentParser(
        description="Compare FlexLock snapshots from various sources"
    )

    # Shared options for every subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--details", action="store_true", help="Show detailed differences (text)"
    )
    common.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )

    subparsers = parser.add_subparsers(
        dest="mode", required=True, help="Comparison mode"
    )

    # Mode 1: Compare two directories (traditional)
    dir_parser = subparsers.add_parser(
        "dirs", parents=[common], help="Compare two directory-based snapshots"
    )
    dir_parser.add_argument("dir1", type=Path, help="First directory")
    dir_parser.add_argument("dir2", type=Path, help="Second directory")

    # Mode 2: Compare two tasks in DB
    db_parser = subparsers.add_parser(
        "db", parents=[common], help="Compare two DB-based snapshots"
    )
    db_parser.add_argument("db_path", type=Path, help="Path to tasks database")
    db_parser.add_argument("task_id1", help="First task ID (hash)")
    db_parser.add_argument("task_id2", help="Second task ID (hash)")

    # Mode 3: Compare directory to DB task
    mixed_parser = subparsers.add_parser(
        "mixed", parents=[common], help="Compare directory snapshot to DB snapshot"
    )
    mixed_parser.add_argument("dir_path", type=Path, help="Directory path")
    mixed_parser.add_argument("db_path", type=Path, help="Database path")
    mixed_parser.add_argument("task_id", help="Task ID in database")

    args = parser.parse_args()

    try:
        if args.mode == "dirs":
            if not args.dir1.exists():
                logger.error(f"Directory not found: {args.dir1}")
                sys.exit(2)
            if not args.dir2.exists():
                logger.error(f"Directory not found: {args.dir2}")
                sys.exit(2)
            snap1 = load_snapshot_from_dir(args.dir1)
            snap2 = load_snapshot_from_dir(args.dir2)

        elif args.mode == "db":
            if not args.db_path.exists():
                logger.error(f"Database not found: {args.db_path}")
                sys.exit(2)
            snap1 = load_snapshot_from_db(args.db_path, args.task_id1)
            snap2 = load_snapshot_from_db(args.db_path, args.task_id2)

        elif args.mode == "mixed":
            if not args.dir_path.exists():
                logger.error(f"Directory not found: {args.dir_path}")
                sys.exit(2)
            if not args.db_path.exists():
                logger.error(f"Database not found: {args.db_path}")
                sys.exit(2)
            snap1 = load_snapshot_from_dir(args.dir_path)
            snap2 = load_snapshot_from_db(args.db_path, args.task_id)

        if args.format == "json":
            is_match, diffs = run_comparison(snap1, snap2)
            print(json.dumps({"match": is_match, "diffs": diffs}, indent=2, default=str))
        else:
            is_match = compare_snapshots(snap1, snap2, args.details)

        # 0 match / 1 differ.
        sys.exit(0 if is_match else 1)

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
