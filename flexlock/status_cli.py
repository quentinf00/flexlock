"""CLI for monitoring FlexLock task database status."""

import argparse
import sys
import time
from pathlib import Path
from loguru import logger
from flexlock.taskdb import (
    get_status_counts,
    get_status_counts_by_tag,
    get_failed_tasks,
    get_all_tasks,
)


def print_status_summary(db_path: Path, tags=None, label: str = ""):
    """Print summary of task statuses, optionally scoped to ``tags``."""
    status_counts = get_status_counts(db_path, tags=tags)

    pending = status_counts.get("pending", 0)
    running = status_counts.get("running", 0)
    done = status_counts.get("done", 0)
    failed = status_counts.get("failed", 0)
    interrupted = status_counts.get("interrupted", 0)
    total = pending + running + done + failed + interrupted

    header = f"Task Status Summary{label}"
    print("\n" + "=" * 60)
    print(header)
    print("=" * 60)
    print(f"Pending:      {pending:>5}")
    print(f"Running:      {running:>5}")
    print(f"Done:         {done:>5}")
    print(f"Failed:       {failed:>5}")
    print(f"Interrupted:  {interrupted:>5}")
    print("-" * 60)
    print(f"Total:        {total:>5}")

    if total > 0:
        terminal = done + failed + interrupted
        progress = terminal / total * 100
        print(f"Progress:     {progress:>5.1f}% ({terminal}/{total} completed)")

        if pending == 0 and running == 0:
            issues = failed + interrupted
            if issues:
                label_parts = []
                if failed:
                    label_parts.append(f"{failed} failed")
                if interrupted:
                    label_parts.append(f"{interrupted} interrupted")
                print(f"\nStatus:     ⚠️  Finished with issues ({', '.join(label_parts)})")
            else:
                print(f"\nStatus:     ✓  All tasks completed successfully")
        elif pending == 0 and running > 0:
            print(f"\nStatus:     ⚠️  {running} task(s) running with no pending — possible zombie(s)")
        else:
            print(f"\nStatus:     ⏳ In progress")

    print("=" * 60 + "\n")


def print_tags_breakdown(db_path: Path):
    """Print a per-tag status breakdown table."""
    by_tag = get_status_counts_by_tag(db_path)
    if not by_tag:
        print("No tasks found in DB.\n")
        return

    print("\n" + "=" * 60)
    print("Per-Tag Status Breakdown")
    print("=" * 60)

    for tag, counts in sorted(by_tag.items(), key=lambda x: (x[0] is None, x[0])):
        tag_label = repr(tag) if tag is not None else "(untagged)"
        pending = counts.get("pending", 0)
        running = counts.get("running", 0)
        done = counts.get("done", 0)
        failed = counts.get("failed", 0)
        interrupted = counts.get("interrupted", 0)
        total = pending + running + done + failed + interrupted
        terminal = done + failed + interrupted
        pct = terminal / total * 100 if total else 0

        print(f"\nTag: {tag_label}  ({total} total, {pct:.1f}% done)")
        print(f"  pending={pending}  running={running}  done={done}  "
              f"failed={failed}  interrupted={interrupted}")

    print("\n" + "=" * 60 + "\n")


def print_failed_tasks(db_path: Path, verbose: bool = False, tags=None):
    """Print details of failed and interrupted tasks."""
    failed_tasks = get_failed_tasks(db_path, tags=tags)

    if not failed_tasks:
        print("No failed or interrupted tasks found.\n")
        return

    print(f"\nFailed / Interrupted Tasks ({len(failed_tasks)})")
    print("=" * 60)

    for i, task_info in enumerate(failed_tasks, 1):
        status = task_info.get("status", "failed")
        print(f"\nTask #{i}  [{status.upper()}]")
        print("-" * 60)

        task = task_info["task"]
        print("Config:")
        for key, value in task.items():
            if not key.startswith("_"):
                print(f"  {key}: {value}")

        error = task_info["error"]
        if error:
            print(f"\nError:")
            if len(error) > 500 and not verbose:
                print(f"  {error[:500]}...")
                print(f"  (Use --verbose to see full error)")
            else:
                for line in error.split("\n"):
                    print(f"  {line}")

        if task_info["node"]:
            print(f"\nNode: {task_info['node']}")
        if task_info["ts_start"]:
            print(f"Started:  {task_info['ts_start']}")
        if task_info["ts_end"]:
            print(f"Finished: {task_info['ts_end']}")

    print("\n" + "=" * 60 + "\n")


def print_all_tasks(db_path: Path, status_filter: str = None, tags=None):
    """Print all tasks, optionally filtered by status and/or tag."""
    tasks = get_all_tasks(db_path, status=status_filter, tags=tags)

    filter_desc = f" ({status_filter})" if status_filter else ""
    print(f"\nAll Tasks{filter_desc} ({len(tasks)})")
    print("=" * 60)

    if not tasks:
        print("No tasks found.\n")
        return

    print(f"{'Status':<13} {'Task ID':<12} {'Node':<15} {'Timestamp'}")
    print("-" * 60)

    for task_info in tasks:
        status = task_info["status"]
        task_id = task_info["task_id"][:10]
        node = task_info["node"] or "N/A"
        node = node[:13] if len(node) > 13 else node
        timestamp = task_info["ts_end"] or task_info["ts_start"] or "N/A"
        if timestamp != "N/A":
            timestamp = timestamp[:19]

        print(f"{status:<13} {task_id:<12} {node:<15} {timestamp}")

    print("=" * 60 + "\n")


def watch_status(db_path: Path, interval: int = 10, tags=None):
    """Watch task status in real-time, optionally scoped to ``tags``."""
    print("Watching task status (Ctrl+C to stop)...\n")

    try:
        while True:
            print("\033[2J\033[H", end="")

            from datetime import datetime
            print(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            print_status_summary(db_path, tags=tags)

            status_counts = get_status_counts(db_path, tags=tags)
            pending = status_counts.get("pending", 0)
            running = status_counts.get("running", 0)

            if pending == 0 and running == 0:
                print("All tasks reached a terminal state. Exiting watch mode.\n")
                break

            print(f"Refreshing in {interval}s... (Ctrl+C to stop)")
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nWatch mode stopped.\n")


def main():
    """CLI entry point for flexlock-status command."""
    parser = argparse.ArgumentParser(
        description="Monitor FlexLock task database status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show status summary
  flexlock-status outputs/sweep/run.lock.tasks.db

  # Per-tag breakdown (useful when multiple sweeps share a DB)
  flexlock-status outputs/sweep/run.lock.tasks.db --tags

  # Scope the entire view to one tag
  flexlock-status outputs/sweep/run.lock.tasks.db --tag extract

  # Show failed / interrupted tasks
  flexlock-status outputs/sweep/run.lock.tasks.db --failed

  # Show all tasks
  flexlock-status outputs/sweep/run.lock.tasks.db --all

  # Filter by status
  flexlock-status outputs/sweep/run.lock.tasks.db --all --status interrupted

  # Watch status in real-time (scoped to a tag)
  flexlock-status outputs/sweep/run.lock.tasks.db --watch --tag collocate
        """,
    )

    parser.add_argument(
        "db_path", type=Path, help="Path to task database (run.lock.tasks.db)"
    )
    parser.add_argument(
        "--failed", action="store_true", help="Show details of failed / interrupted tasks"
    )
    parser.add_argument("--all", action="store_true", help="Show all tasks")
    parser.add_argument(
        "--status",
        choices=["pending", "running", "done", "failed", "interrupted"],
        help="Filter tasks by status (use with --all)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch status in real-time (updates every 10s)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Update interval for watch mode in seconds (default: 10)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show verbose output (full error messages)",
    )
    parser.add_argument(
        "--tag",
        metavar="NAME",
        help="Scope the entire view (summary, --failed, --all, --watch) to a "
             "single tag. Useful to monitor one sweep inside a shared DB.",
    )
    parser.add_argument(
        "--tags",
        action="store_true",
        dest="show_tags",
        help="Print a per-tag status breakdown before the global summary. "
             "Useful to discover which tags exist and what to pass to "
             "flexlock-worker --tags.",
    )

    args = parser.parse_args()

    if not args.db_path.exists():
        logger.error(f"Database not found: {args.db_path}")
        sys.exit(1)

    # --tag NAME scopes everything; convert to a list for the taskdb API.
    scope_tags = [args.tag] if args.tag else None
    tag_label = f" [tag={args.tag!r}]" if args.tag else ""

    try:
        if args.watch:
            watch_status(args.db_path, args.interval, tags=scope_tags)
        elif args.failed:
            if args.show_tags:
                print_tags_breakdown(args.db_path)
            print_status_summary(args.db_path, tags=scope_tags, label=tag_label)
            print_failed_tasks(args.db_path, verbose=args.verbose, tags=scope_tags)
        elif args.all:
            if args.show_tags:
                print_tags_breakdown(args.db_path)
            print_status_summary(args.db_path, tags=scope_tags, label=tag_label)
            print_all_tasks(args.db_path, status_filter=args.status, tags=scope_tags)
        else:
            if args.show_tags:
                print_tags_breakdown(args.db_path)
            print_status_summary(args.db_path, tags=scope_tags, label=tag_label)

    except Exception as e:
        logger.error(f"Error reading database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
