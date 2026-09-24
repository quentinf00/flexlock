"""SQLite-based task database for FlexLock parallel execution."""

from pathlib import Path
import random
import sqlite3
import time
from omegaconf import OmegaConf, DictConfig, ListConfig
import threading
from loguru import logger
import yaml
import hashlib
from contextlib import contextmanager
from typing import Any, List

from . import config as _config

_thread_local_conns = threading.local()


def _tag_filter(tag):
    """Return (sql_fragment, params) for an optional tag scope.

    tag=None  -> no filter (matches all rows, including legacy NULL rows).
    str       -> single tag: AND tag = ?
    list/tuple/set -> AND tag IN (?, ?, ...)  — empty collection = no filter.

    The returned fragment is prefixed with 'AND ' and is '' when tag is None.
    """
    if tag is None:
        return "", []
    if isinstance(tag, (list, tuple, set)):
        tags = list(tag)
        if not tags:
            return "", []
        placeholders = ",".join("?" for _ in tags)
        return f"AND tag IN ({placeholders})", tags
    return "AND tag = ?", [tag]


def _hash_task(task: Any) -> str:
    """Generate a stable SHA1 id for a task.

    The id must be invariant across the ``_to_yaml``/``_from_yaml`` roundtrip
    and across plain-dict vs ``DictConfig`` representations. ``str(task)`` is
    neither: YAML serialization reorders keys, so a task claimed back from the
    DB would hash differently than when it was queued — which silently breaks
    ``finish_task`` (it can't find the row to mark done). Canonicalize to a
    sorted-key JSON string first.
    """
    import json as _json

    if isinstance(task, (DictConfig, ListConfig)):
        obj = OmegaConf.to_container(task, resolve=False)
    else:
        obj = task
    try:
        canonical = _json.dumps(obj, sort_keys=True, default=str)
    except TypeError:
        canonical = str(obj)
    return hashlib.sha1(canonical.encode()).hexdigest()


def _to_yaml(value: Any) -> str:
    """Serialize any value to a YAML string without !! Python tags.

    OmegaConf containers are serialized via OmegaConf.to_yaml (handles
    interpolation correctly). Everything else — scalars, plain dicts/lists —
    goes through yaml.safe_dump, which raises RepresenterError on arbitrary
    Python objects instead of emitting !!python/object tags.
    """
    if isinstance(value, (DictConfig, ListConfig)):
        return OmegaConf.to_yaml(value)
    return yaml.safe_dump(value, default_flow_style=False)


def _from_yaml(text: str) -> Any:
    """Deserialize a YAML string back to a task or result value.

    Mappings are wrapped in OmegaConf.create so the rest of the codebase
    can treat them as DictConfig. Scalars and lists are returned as-is.
    """
    obj = yaml.safe_load(text)
    if isinstance(obj, dict):
        return OmegaConf.create(obj)
    return obj


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
            # Autocommit mode: write transactions are managed explicitly by
            # _write_txn (BEGIN IMMEDIATE), reads run without a transaction.
            c = sqlite3.connect(
                db_path_str, check_same_thread=False, isolation_level=None
            )
            # Set PRAGMA for better performance and concurrency.
            c.execute("PRAGMA journal_mode=DELETE")
            c.execute("PRAGMA busy_timeout=30000")
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
                    ts_end DATETIME,
                    snapshot TEXT,
                    job_id TEXT,
                    tag TEXT
                )
                """
            )

            # Auto-migration: add columns introduced after the initial schema.
            cursor = c.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]
            for col, ddl in [
                ("snapshot", "ALTER TABLE tasks ADD COLUMN snapshot TEXT"),
                ("job_id",   "ALTER TABLE tasks ADD COLUMN job_id TEXT"),
                ("tag",      "ALTER TABLE tasks ADD COLUMN tag TEXT"),
            ]:
                if col not in columns:
                    logger.debug(f"Adding {col} column to {db_path_str}")
                    c.execute(ddl)
                    c.commit()

            c.execute(
                "CREATE INDEX IF NOT EXISTS ix_tasks_tag_status "
                "ON tasks(tag, status)"
            )
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


def _write_txn(db_path: Path, op):
    """Run ``op(conn)`` in a BEGIN IMMEDIATE transaction, retrying on lock.

    ``busy_timeout`` alone is not enough with many workers on one DB: a
    deferred transaction upgrading SHARED->RESERVED returns SQLITE_BUSY
    immediately (bypassing the timeout), and fcntl locks on network
    filesystems (NFS/Lustre) can fail spuriously. BEGIN IMMEDIATE takes the
    write lock up front, and this loop adds jittered exponential backoff on
    top of busy_timeout. Retrying re-runs ``op`` from scratch, so ``op``
    must be a pure function of its statements (no external side effects).
    """
    delay = 0.05
    attempts = max(1, _config.DB_RETRY_ATTEMPTS)
    for attempt in range(attempts):
        try:
            with _conn(db_path) as c:
                try:
                    c.execute("BEGIN IMMEDIATE")
                    out = op(c)
                    c.commit()
                    return out
                except BaseException:
                    c.rollback()
                    raise
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "locked" not in msg and "busy" not in msg:
                raise
            if attempt == attempts - 1:
                raise
            sleep = random.uniform(delay, 2 * delay)
            logger.debug(
                f"{db_path} locked ({e}); retry {attempt + 1}/{attempts} "
                f"in {sleep:.2f}s"
            )
            time.sleep(sleep)
            delay = min(delay * 2, _config.DB_RETRY_MAX_BACKOFF)


def reset_db(db_path: Path) -> None:
    """Delete a task DB (and its WAL/SHM files) so its tasks are re-queued.

    Closes this thread's cached connection first: otherwise ``_conn`` keeps
    writing to the unlinked inode and the path is never recreated.
    """
    db_path = Path(db_path)
    conns = getattr(_thread_local_conns, "conns", None)
    if conns:
        c = conns.pop(str(db_path.resolve()), None)
        if c is not None:
            try:
                c.close()
            except sqlite3.Error:
                pass
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)


def queue_tasks(db_path: Path, tasks: List[Any], tag: str | None = None) -> None:
    """Adds a list of tasks to the database if they don't already exist.

    ``tag`` scopes these rows to a particular sweep so concurrent sweeps (or a
    parent pipeline job) sharing the same DB don't interfere with each other.

    Note: ``task_id`` is a content hash of the task dict. If two sweeps queue
    an *identical* task dict they share one row; ``INSERT OR IGNORE`` keeps the
    first tag. That only happens when the work is truly identical, which is
    acceptable.
    """
    rows = [(_hash_task(t), _to_yaml(t), tag) for t in tasks]

    def op(c):
        c.executemany(
            "INSERT OR IGNORE INTO tasks (task_id, task_info, tag) VALUES (?, ?, ?)",
            rows,
        )

    _write_txn(db_path, op)


def claim_next_tasks(
    db_path: Path,
    node: str,
    job_id: str | None = None,
    tags=None,
    n: int = 1,
) -> List[Any]:
    """Claims up to ``n`` pending tasks in one write transaction.

    Batching is the main lever against DB contention at scale: with many
    workers, one claim transaction per batch instead of per task divides
    the write-lock traffic by ``n``. Returns the claimed tasks (possibly
    fewer than ``n``, empty when nothing is pending).

    ``node`` and ``job_id`` record which worker/scheduler job owns the tasks,
    so the controller can later reconcile orphaned tasks against the OS/
    scheduler's view of worker liveness (no self-reported heartbeat needed).

    ``tags`` restricts the claim to rows whose ``tag`` matches (``None``
    claims any row, preserving backwards-compatible behaviour for untagged DBs).
    """
    tag_frag, tag_params = _tag_filter(tags)

    def op(c):
        cur = c.execute(
            f"""
            UPDATE tasks
               SET status='running',
                   node=?,
                   job_id=?,
                   ts_start=CURRENT_TIMESTAMP
            WHERE task_id IN (
                SELECT task_id FROM tasks
                WHERE status='pending' {tag_frag}
                LIMIT ?
            )
            RETURNING task_info
            """,
            (node, job_id, *tag_params, n),
        )
        return [r[0] for r in cur.fetchall()]

    return [_from_yaml(r) for r in _write_txn(db_path, op)]


def claim_next_task(
    db_path: Path,
    node: str,
    job_id: str | None = None,
    tags=None,
) -> Any | None:
    """Claims the next available pending task and marks it as running.

    Single-task convenience wrapper over ``claim_next_tasks``.
    """
    tasks = claim_next_tasks(db_path, node, job_id=job_id, tags=tags, n=1)
    return tasks[0] if tasks else None


def finish_tasks(db_path: Path, entries: List[dict]) -> None:
    """Marks a batch of tasks finished in one write transaction.

    Each entry is a dict with key ``task`` (required) and optional ``error``,
    ``result``, ``status`` — same semantics as ``finish_task``. Workers
    buffer per-task outcomes and flush them here once per claimed batch.
    """
    rows = []
    for e in entries:
        error = e.get("error")
        status = e.get("status") or ("failed" if error else "done")
        result = e.get("result")
        rows.append(
            (
                status,
                error,
                _to_yaml(result) if result is not None else None,
                _hash_task(e["task"]),
            )
        )
    if not rows:
        return

    def op(c):
        c.executemany(
            "UPDATE tasks SET status=?, error=?, result_info=?, ts_end=CURRENT_TIMESTAMP WHERE task_id=?",
            rows,
        )

    _write_txn(db_path, op)


def finish_task(
    db_path: Path,
    task: Any,
    error: str | None = None,
    result: Any | None = None,
    status: str | None = None,
) -> None:
    """Marks a task as finished and records its result or error.

    ``status`` defaults to ``'done'`` on success, ``'failed'`` on error.
    Pass ``status='interrupted'`` when the worker was killed mid-task.
    """
    finish_tasks(db_path, [dict(task=task, error=error, result=result, status=status)])


def _update_running(
    db_path: Path,
    new_status: str,
    job_id: str | None = None,
    tags=None,
    error: str | None = None,
) -> int:
    """Move ``running`` tasks to ``new_status``; optionally scope to job/tags.

    Returns the number of rows updated. Shared by the controller (which marks
    orphans 'interrupted') and the reclaim path (which resets them 'pending').
    """
    tag_frag, tag_params = _tag_filter(tags)
    clauses = [f"status='running' {tag_frag}"]
    params: list = list(tag_params)
    if job_id is not None:
        clauses.append("job_id=?")
        params.append(job_id)
    where = " AND ".join(c for c in clauses if c)

    if new_status == "pending":
        # Clear ownership so the task is freely claimable again.
        set_clause = "status='pending', node=NULL, job_id=NULL, ts_start=NULL"
        set_params: list = []
    else:
        set_clause = "status=?, error=?, ts_end=CURRENT_TIMESTAMP"
        set_params = [new_status, error]

    def op(c):
        cur = c.execute(
            f"UPDATE tasks SET {set_clause} WHERE {where}",
            (*set_params, *params),
        )
        return cur.rowcount

    return _write_txn(db_path, op)


def mark_orphans_interrupted(
    db_path: Path, job_id: str | None = None, tags=None
) -> int:
    """Mark still-``running`` tasks as ``interrupted``.

    Called by the controller once it knows the owning worker(s) are dead
    (local processes joined, or the HPC job left the scheduler's active set).
    ``tags`` limits the reconcile to this sweep's rows so a parent pipeline
    row in the same DB is never touched. Returns the number of tasks marked.
    """
    return _update_running(
        db_path, "interrupted", job_id=job_id, tags=tags,
        error="Worker died before the task finished (orphaned).",
    )


def reclaim_running(db_path: Path, job_id: str | None = None, tags=None) -> int:
    """Reset ``running`` tasks back to ``pending`` so they can be re-claimed.

    Used by ``flexlock-worker --reclaim`` to recover tasks stranded by a
    previous worker that died without cleanup. ``tags`` limits the reclaim
    to the specified sweep. Returns the number reset.
    """
    return _update_running(db_path, "pending", job_id=job_id, tags=tags)


def pending_count(db_path: Path, tags=None) -> int:
    """Returns the number of pending tasks in the database.

    ``tags`` restricts the count to rows matching the given tag(s).
    """
    tag_frag, tag_params = _tag_filter(tags)
    with _conn(db_path) as c:
        return c.execute(
            f"SELECT COUNT(*) FROM tasks WHERE status='pending' {tag_frag}",
            tag_params,
        ).fetchone()[0]


def dump_to_yaml(db_path: Path, yaml_path: Path, tags=None) -> None:
    """Dumps all terminal (done/failed/interrupted) tasks and their results to a YAML file.

    ``tags`` restricts the dump to the specified sweep's rows so each sweep
    writes only its own results.
    """
    tag_frag, tag_params = _tag_filter(tags)
    with _conn(db_path) as c:
        logger.debug(f"using {c} for {db_path}")
        rows = c.execute(
            f"SELECT result_info, task_info, status FROM tasks "
            f"WHERE status IN ('done','failed','interrupted') {tag_frag} "
            f"ORDER BY ts_end",
            tag_params,
        ).fetchall()
        data = [
            dict(task=_from_yaml(r[0]), status=r[2])
            if r[0]
            else dict(task=_from_yaml(r[1]), status=r[2])
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

    payload = json.dumps(snapshot_data)

    def op(c):
        c.execute(
            "UPDATE tasks SET snapshot=? WHERE task_id=?",
            (payload, task_id),
        )

    _write_txn(db_path, op)


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


def get_task_status(db_path: Path, task_id: str) -> dict | None:
    """Return a single task's status row, or ``None`` if not found.

    Thin SELECT used by the query layer to classify a sweep-task dir from its
    ``.flexlock_marker`` without loading the whole DB.
    """
    with _conn(db_path) as c:
        cur = c.execute(
            "SELECT status, error, node, ts_start, ts_end FROM tasks WHERE task_id=?",
            (task_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "status": row[0],
            "error": row[1],
            "node": row[2],
            "ts_start": row[3],
            "ts_end": row[4],
        }


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


def get_status_counts(db_path: Path, tags=None) -> dict:
    """Get counts of tasks by status.

    Returns a dict with keys for every status that has at least one task,
    always including 'pending', 'running', 'done', 'failed', 'interrupted'
    (defaulting to 0 when absent).

    ``tags`` restricts the counts to the specified sweep's rows.
    """
    tag_frag, tag_params = _tag_filter(tags)
    with _conn(db_path) as c:
        rows = c.execute(
            f"SELECT status, COUNT(*) as count FROM tasks "
            f"WHERE 1=1 {tag_frag} GROUP BY status",
            tag_params,
        ).fetchall()
    counts = {row[0]: row[1] for row in rows}
    for key in ("pending", "running", "done", "failed", "interrupted"):
        counts.setdefault(key, 0)
    return counts


def get_status_counts_by_tag(db_path: Path) -> dict:
    """Get per-tag status counts for all rows in the DB.

    Returns ``{tag: {status: count, ...}}`` where ``tag`` may be ``None``
    for legacy untagged rows. Each inner dict is zero-filled for the five
    standard statuses.
    """
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT tag, status, COUNT(*) FROM tasks GROUP BY tag, status"
        ).fetchall()
    result: dict = {}
    for tag, status, count in rows:
        bucket = result.setdefault(tag, {})
        bucket[status] = count
    for bucket in result.values():
        for key in ("pending", "running", "done", "failed", "interrupted"):
            bucket.setdefault(key, 0)
    return result


def get_failed_tasks(db_path: Path, tags=None) -> list:
    """Get details of failed and interrupted tasks.

    ``tags`` restricts results to the specified sweep's rows.

    Returns:
        list: List of dicts with task info, error, and timestamps
    """
    tag_frag, tag_params = _tag_filter(tags)
    with _conn(db_path) as c:
        rows = c.execute(
            f"""
            SELECT task_info, error, ts_start, ts_end, node, status
            FROM tasks WHERE status IN ('failed', 'interrupted') {tag_frag}
            ORDER BY ts_end DESC
            """,
            tag_params,
        ).fetchall()

        failed_tasks = []
        for row in rows:
            task_info = _from_yaml(row[0]) if row[0] else {}
            failed_tasks.append(
                {
                    "task": task_info,
                    "error": row[1],
                    "ts_start": row[2],
                    "ts_end": row[3],
                    "node": row[4],
                    "status": row[5],
                }
            )
        return failed_tasks


def get_all_tasks(db_path: Path, status: str = None, tags=None) -> list:
    """Get all tasks, optionally filtered by status and/or tag.

    Args:
        db_path: Path to database
        status: Optional status filter ('pending', 'running', 'done', 'failed', 'interrupted')
        tags: Optional tag filter (str or list of str); ``None`` returns all rows.

    Returns:
        list: List of dicts with task details
    """
    tag_frag, tag_params = _tag_filter(tags)
    with _conn(db_path) as c:
        if status:
            rows = c.execute(
                f"""
                SELECT task_id, task_info, result_info, status, error,
                       ts_start, ts_end, node
                FROM tasks WHERE status=? {tag_frag}
                ORDER BY ts_start DESC
                """,
                (status, *tag_params),
            ).fetchall()
        else:
            rows = c.execute(
                f"""
                SELECT task_id, task_info, result_info, status, error,
                       ts_start, ts_end, node
                FROM tasks WHERE 1=1 {tag_frag}
                ORDER BY ts_start DESC
                """,
                tag_params,
            ).fetchall()

        tasks = []
        for row in rows:
            task_info = _from_yaml(row[1]) if row[1] else {}
            result_info = _from_yaml(row[2]) if row[2] else {}
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

    def _to_primitive(v):
        if isinstance(v, (DictConfig, ListConfig)):
            return OmegaConf.to_container(v, resolve=True)
        if isinstance(v, dict):
            return {k: _to_primitive(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_to_primitive(i) for i in v]
        return v

    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp-")
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(_to_primitive(data), f, default_flow_style=False)
    os.rename(tmp, path)
