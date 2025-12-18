"""CLI for monitoring FlexLock task database status."""

import argparse
import sys
import time
from pathlib import Path
from loguru import logger
from flexlock.taskdb import get_status_counts, get_failed_tasks, get_all_tasks


def print_status_summary(db_path: Path):
    """Print summary of task statuses."""
    status_counts = get_status_counts(db_path)

    # Get totals
    pending = status_counts.get('pending', 0)
    running = status_counts.get('running', 0)
    done = status_counts.get('done', 0)
    failed = status_counts.get('failed', 0)
    total = pending + running + done + failed

    # Print header
    print("\n" + "=" * 60)
    print("Task Status Summary")
    print("=" * 60)

    # Print counts
    print(f"Pending:    {pending:>5}")
    print(f"Running:    {running:>5}")
    print(f"Done:       {done:>5}")
    print(f"Failed:     {failed:>5}")
    print("-" * 60)
    print(f"Total:      {total:>5}")

    # Print progress
    if total > 0:
        completed = done + failed
        progress = completed / total * 100
        print(f"Progress:   {progress:>5.1f}% ({completed}/{total} completed)")

        # Show status
        if pending == 0 and running == 0:
            if failed > 0:
                print(f"\nStatus:     ⚠️  Completed with {failed} failures")
            else:
                print(f"\nStatus:     ✓  All tasks completed successfully")
        else:
            print(f"\nStatus:     ⏳ In progress")

    print("=" * 60 + "\n")


def print_failed_tasks(db_path: Path, verbose: bool = False):
    """Print details of failed tasks."""
    failed_tasks = get_failed_tasks(db_path)

    if not failed_tasks:
        print("No failed tasks found.\n")
        return

    print(f"\nFailed Tasks ({len(failed_tasks)})")
    print("=" * 60)

    for i, task_info in enumerate(failed_tasks, 1):
        print(f"\nTask #{i}")
        print("-" * 60)

        # Print task configuration
        task = task_info['task']
        print("Config:")
        for key, value in task.items():
            if not key.startswith('_'):
                print(f"  {key}: {value}")

        # Print error
        error = task_info['error']
        if error:
            print(f"\nError:")
            # Truncate very long errors
            if len(error) > 500 and not verbose:
                print(f"  {error[:500]}...")
                print(f"  (Use --verbose to see full error)")
            else:
                for line in error.split('\n'):
                    print(f"  {line}")

        # Print metadata
        if task_info['node']:
            print(f"\nNode: {task_info['node']}")
        if task_info['ts_start']:
            print(f"Started:  {task_info['ts_start']}")
        if task_info['ts_end']:
            print(f"Finished: {task_info['ts_end']}")

    print("\n" + "=" * 60 + "\n")


def print_all_tasks(db_path: Path, status_filter: str = None):
    """Print all tasks, optionally filtered by status."""
    tasks = get_all_tasks(db_path, status=status_filter)

    filter_desc = f" ({status_filter})" if status_filter else ""
    print(f"\nAll Tasks{filter_desc} ({len(tasks)})")
    print("=" * 60)

    if not tasks:
        print("No tasks found.\n")
        return

    # Print table header
    print(f"{'Status':<10} {'Task ID':<12} {'Node':<15} {'Timestamp'}")
    print("-" * 60)

    for task_info in tasks:
        status = task_info['status']
        task_id = task_info['task_id'][:10]  # Truncate hash
        node = task_info['node'] or 'N/A'
        node = node[:13] if len(node) > 13 else node
        timestamp = task_info['ts_end'] or task_info['ts_start'] or 'N/A'

        # Format timestamp
        if timestamp != 'N/A':
            timestamp = timestamp[:19]  # Just YYYY-MM-DD HH:MM:SS

        print(f"{status:<10} {task_id:<12} {node:<15} {timestamp}")

    print("=" * 60 + "\n")


def watch_status(db_path: Path, interval: int = 10):
    """Watch task status in real-time."""
    print("Watching task status (Ctrl+C to stop)...\n")

    try:
        while True:
            # Clear screen (works on Unix and Windows)
            print("\033[2J\033[H", end="")

            # Print timestamp
            from datetime import datetime
            print(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # Print status
            print_status_summary(db_path)

            # Check if completed
            status_counts = get_status_counts(db_path)
            pending = status_counts.get('pending', 0)
            running = status_counts.get('running', 0)

            if pending == 0 and running == 0:
                print("All tasks completed. Exiting watch mode.\n")
                break

            # Wait before next update
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

  # Show failed tasks
  flexlock-status outputs/sweep/run.lock.tasks.db --failed

  # Show all tasks
  flexlock-status outputs/sweep/run.lock.tasks.db --all

  # Watch status in real-time
  flexlock-status outputs/sweep/run.lock.tasks.db --watch

  # Show verbose error messages
  flexlock-status outputs/sweep/run.lock.tasks.db --failed --verbose
        """
    )

    parser.add_argument(
        "db_path",
        type=Path,
        help="Path to task database (run.lock.tasks.db)"
    )

    parser.add_argument(
        "--failed",
        action="store_true",
        help="Show details of failed tasks"
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all tasks"
    )

    parser.add_argument(
        "--status",
        choices=['pending', 'running', 'done', 'failed'],
        help="Filter tasks by status (use with --all)"
    )

    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch status in real-time (updates every 10s)"
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Update interval for watch mode in seconds (default: 10)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output (full error messages)"
    )

    args = parser.parse_args()

    # Validate database exists
    if not args.db_path.exists():
        logger.error(f"Database not found: {args.db_path}")
        sys.exit(1)

    try:
        if args.watch:
            # Watch mode
            watch_status(args.db_path, args.interval)
        elif args.failed:
            # Show failed tasks
            print_status_summary(args.db_path)
            print_failed_tasks(args.db_path, verbose=args.verbose)
        elif args.all:
            # Show all tasks
            print_status_summary(args.db_path)
            print_all_tasks(args.db_path, status_filter=args.status)
        else:
            # Default: just show summary
            print_status_summary(args.db_path)

    except Exception as e:
        logger.error(f"Error reading database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
