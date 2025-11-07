"""SQLite-based task database for FlexLock parallel execution."""

from pathlib import Path
import sqlite3
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
            c.execute("PRAGMA foreign_keys=ON") # Good practice to enforce foreign key constraints
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
            _thread_local_conns.conns[db_path_str] = c
            logger.debug(f"Created new connection for {db_path_str} in thread {threading.get_ident()}")
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
            [( _hash_task(t), yaml.dump(t) ) for t in tasks],
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
            (node,)
        )
        row = cur.fetchone()
        if row:
            c.commit()
            return yaml.safe_load(row[0])
    return None


def finish_task(db_path: Path, task: Any, error: str | None = None, result: Any | None = None) -> None:
    """Marks a task as finished (done or failed) and records its result or error."""
    tid = _hash_task(task)
    status = "failed" if error else "done"
    result_str = yaml.dump(result) if result is not None else None
    with _conn(db_path) as c:
        c.execute(
            "UPDATE tasks SET status=?, error=?, result_info=?, ts_end=CURRENT_TIMESTAMP WHERE task_id=?",
            (status, error, result_str, tid),
        )
        c.commit()


def pending_count(db_path: Path) -> int:
    """Returns the number of pending tasks in the database."""
    with _conn(db_path) as c:
        return c.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]


def dump_to_yaml(db_path: Path, yaml_path: Path) -> None:
    """Dumps all completed (done or failed) tasks and their results to a YAML file."""
    with _conn(db_path) as c:
        logger.debug(f"using {c} for {db_path}")
        rows = c.execute(
            "SELECT result_info, task_info FROM tasks WHERE status IN ('done','failed') ORDER BY ts_end"
        ).fetchall()
        data = [yaml.safe_load(r[0]) if r[0] else yaml.safe_load(r[1]) for r in rows if r[0] or r[1]]
        logger.debug(f"dumping {rows} to {yaml_path}")

    _atomic_write_yaml(data, yaml_path)


def _atomic_write_yaml(data: list, path: Path):
    import tempfile, os
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp-")
    with os.fdopen(fd, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    os.rename(tmp, path)
