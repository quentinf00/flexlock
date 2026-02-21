"""SQLite-based task database for FlexLock parallel execution."""

from pathlib import Path
import sqlite3
from omegaconf import OmegaConf
import threading
from loguru import logger
import yaml
import hashlib
import logging
from contextlib import contextmanager
from typing import Any, List

logger = logging.getLogger(__name__)
_thread_local_conns = threading.local()


def _hash_task(task: Any) -> str:
    """Generates a SHA1 hash for a given task object."""
    return hashlib.sha1(str(task).encode()).hexdigest()


@contextmanager
def _conn(db_path: Path):
    """
    A thread-safe context manager for SQLite database connections.

    This function maintains a cache of connections per thread. A new connection
    is created for each unique database path and reused for subsequent calls
    with the same path within that thread.
    """
    # Use the absolute path as a reliable key for the connections dictionary.
    db_path_str = str(db_path.resolve())
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize the connections dictionary for the current thread if it doesn't exist.
    if not hasattr(_thread_local_conns, "conns"):
        _thread_local_conns.conns = {}

    # Check if a connection for this specific db_path already exists in the thread's cache.
    if db_path_str not in _thread_local_conns.conns:
        # If not, create a new connection and add it to the cache.
        try:
            c = sqlite3.connect(db_path_str, check_same_thread=False)
            # Set PRAGMA for better performance and concurrency.
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=15000")
            c.execute(
                "PRAGMA foreign_keys=ON"
            )  # Good practice to enforce foreign key constraints
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_info TEXT,
                    result_info TEXT,
                    status TEXT DEFAULT 'pending',
                    node TEXT,
                    error TEXT,
                    ts_start DATETIME,
                    ts_end DATETIME
                )
                """
            )

            # Auto-migration: Add snapshot column if it doesn't exist
            cursor = c.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]
            if "snapshot" not in columns:
                logger.debug(f"Adding snapshot column to {db_path_str}")
                c.execute("ALTER TABLE tasks ADD COLUMN snapshot TEXT")
                c.commit()

            _thread_local_conns.conns[db_path_str] = c
            logger.debug(
                f"Created new connection for {db_path_str} in thread {threading.get_ident()}"
            )
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database {db_path_str}: {e}")
            raise

    # Yield the connection from the thread's cache.
    # A try...finally block is not strictly necessary here because @contextmanager
    # handles resource cleanup, but it makes the intent clear.
    try:
        yield _thread_local_conns.conns[db_path_str]
    finally:
        pass


def queue_tasks(db_path: Path, tasks: List[Any]) -> None:
    """Adds a list of tasks to the database if they don't already exist."""
    with _conn(db_path) as c:
        c.executemany(
            "INSERT OR IGNORE INTO tasks (task_id, task_info) VALUES (?, ?)",
            [(_hash_task(t), OmegaConf.to_yaml(t)) for t in tasks],
        )
        c.commit()


def claim_next_task(db_path: Path, node: str) -> Any | None:
    """Claims the next available pending task from the database and marks it as running."""
    with _conn(db_path) as c:
        cur = c.execute(
            """
            UPDATE tasks SET status='running', node=?, ts_start=CURRENT_TIMESTAMP
            WHERE task_id = (SELECT task_id FROM tasks WHERE status='pending' LIMIT 1)
            RETURNING task_info
            """,
            (node,),
        )
        row = cur.fetchone()
        if row:
            c.commit()
            return OmegaConf.create(row[0])
    return None


def finish_task(
    db_path: Path, task: Any, error: str | None = None, result: Any | None = None
) -> None:
    """Marks a task as finished (done or failed) and records its result or error."""
    tid = _hash_task(task)
    status = "failed" if error else "done"
    result_str = OmegaConf.to_yaml(result) if result is not None else None
    with _conn(db_path) as c:
        c.execute(
            "UPDATE tasks SET status=?, error=?, result_info=?, ts_end=CURRENT_TIMESTAMP WHERE task_id=?",
            (status, error, result_str, tid),
        )
        c.commit()


def pending_count(db_path: Path) -> int:
    """Returns the number of pending tasks in the database."""
    with _conn(db_path) as c:
        return c.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='pending'"
        ).fetchone()[0]


def dump_to_yaml(db_path: Path, yaml_path: Path) -> None:
    """Dumps all completed (done or failed) tasks and their results to a YAML file."""
    with _conn(db_path) as c:
        logger.debug(f"using {c} for {db_path}")
        rows = c.execute(
            "SELECT result_info, task_info, status FROM tasks WHERE status IN ('done','failed') ORDER BY ts_end"
        ).fetchall()
        data = [
            dict(task=OmegaConf.create(r[0]), status=r[2])
            if r[0]
            else dict(task=OmegaConf.create(r[1]), status=r[2])
            for r in rows
            if r[0] or r[1]
        ]
        logger.debug(f"dumping {rows} to {yaml_path}")

    _atomic_write_yaml(data, yaml_path)


def update_task_snapshot(db_path: Path, task_id: str, snapshot_data: dict) -> None:
    """
    Updates the snapshot column for a specific task.

    Args:
        db_path: Path to SQLite database
        task_id: Hash of the task (from _hash_task)
        snapshot_data: Complete snapshot dictionary
    """
    import json

    with _conn(db_path) as c:
        c.execute(
            "UPDATE tasks SET snapshot=? WHERE task_id=?",
            (json.dumps(snapshot_data), task_id),
        )
        c.commit()


def get_task_snapshot(db_path: Path, task_id: str) -> dict | None:
    """
    Retrieves the snapshot for a specific task from the database.

    Args:
        db_path: Path to SQLite database
        task_id: Hash of the task (from _hash_task)

    Returns:
        dict: Snapshot data, or None if not found
    """
    import json

    with _conn(db_path) as c:
        cur = c.execute("SELECT snapshot FROM tasks WHERE task_id=?", (task_id,))
        row = cur.fetchone()
        if row and row[0]:
            return json.loads(row[0])
    return None


def list_task_snapshots(db_path: Path, status: str = None) -> List[tuple]:
    """
    Lists all tasks with their snapshots.

    Args:
        db_path: Path to SQLite database
        status: Optional filter by status (pending, running, done, failed)

    Returns:
        List of tuples: (task_id, snapshot_dict, status)
    """
    import json

    with _conn(db_path) as c:
        if status:
            cur = c.execute(
                "SELECT task_id, snapshot, status FROM tasks WHERE status=? AND snapshot IS NOT NULL",
                (status,),
            )
        else:
            cur = c.execute(
                "SELECT task_id, snapshot, status FROM tasks WHERE snapshot IS NOT NULL"
            )

        rows = cur.fetchall()
        return [(r[0], json.loads(r[1]) if r[1] else None, r[2]) for r in rows]


def get_status_counts(db_path: Path) -> dict:
    """
    Get counts of tasks by status.

    Returns:
        dict: Status counts {'pending': N, 'running': N, 'done': N, 'failed': N}
    """
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
        ).fetchall()
        return {row[0]: row[1] for row in rows}


def get_failed_tasks(db_path: Path) -> list:
    """
    Get details of all failed tasks.

    Returns:
        list: List of dicts with task info, error, and timestamps
    """
    with _conn(db_path) as c:
        rows = c.execute(
            """
            SELECT task_info, error, ts_start, ts_end, node
            FROM tasks WHERE status='failed'
            ORDER BY ts_end DESC
            """
        ).fetchall()

        failed_tasks = []
        for row in rows:
            task_info = OmegaConf.create(row[0]) if row[0] else {}
            failed_tasks.append(
                {
                    "task": task_info,
                    "error": row[1],
                    "ts_start": row[2],
                    "ts_end": row[3],
                    "node": row[4],
                }
            )
        return failed_tasks


def get_all_tasks(db_path: Path, status: str = None) -> list:
    """
    Get all tasks, optionally filtered by status.

    Args:
        db_path: Path to database
        status: Optional status filter ('pending', 'running', 'done', 'failed')

    Returns:
        list: List of dicts with task details
    """
    with _conn(db_path) as c:
        if status:
            rows = c.execute(
                """
                SELECT task_id, task_info, result_info, status, error,
                       ts_start, ts_end, node
                FROM tasks WHERE status=?
                ORDER BY ts_start DESC
                """,
                (status,),
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT task_id, task_info, result_info, status, error,
                       ts_start, ts_end, node
                FROM tasks
                ORDER BY ts_start DESC
                """
            ).fetchall()

        tasks = []
        for row in rows:
            task_info = OmegaConf.create(row[1]) if row[1] else {}
            result_info = OmegaConf.create(row[2]) if row[2] else {}
            tasks.append(
                {
                    "task_id": row[0],
                    "task": task_info,
                    "result": result_info,
                    "status": row[3],
                    "error": row[4],
                    "ts_start": row[5],
                    "ts_end": row[6],
                    "node": row[7],
                }
            )
        return tasks


def _atomic_write_yaml(data: list, path: Path):
    import tempfile, os

    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp-")
    with os.fdopen(fd, "w") as f:
        f.write(OmegaConf.to_yaml(data))
    os.rename(tmp, path)
