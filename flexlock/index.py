"""Project-wide fingerprint index — makes cache lookups O(1) and sweep items
first-class.

The index is a **derived cache**: ``run.lock`` (and the task DB) stay
authoritative and the index can always be deleted and rebuilt with
``flexlock reindex``. It maps a run :mod:`fingerprint` to *where* a completed
run lives — either a ``run.lock`` directory (serial/single runs) or a
``(task_db, task_id)`` pair (sweep tasks) — so a config first run as a sweep
task cache-hits when re-run serially, and vice-versa.

Only ``status='done'`` rows are ever served, so failed or interrupted runs are
never returned as cache hits.

Location resolution (see :func:`resolve_index_path`):
  1. ``$FLEXLOCK_INDEX`` if set;
  2. the nearest existing ``.flexlock/index.db`` walking up from ``base``;
  3. otherwise ``<base>/.flexlock/index.db``.

Writers on the read and write paths must resolve to the *same* file for a hit
to land — a project wrapper should set ``search_dirs`` and the index root to
agree (or set ``$FLEXLOCK_INDEX``).
"""

import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

INDEX_DIRNAME = ".flexlock"
INDEX_FILENAME = "index.db"

LOCATION_RUN_LOCK = "run_lock"
LOCATION_TASK = "task"

STATUS_DONE = "done"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    fingerprint   TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    location_kind TEXT NOT NULL,
    run_lock_path TEXT,
    task_db_path  TEXT,
    task_id       TEXT,
    save_dir      TEXT,
    ts            REAL
)
"""


@dataclass
class IndexRow:
    fingerprint: str
    status: str
    location_kind: str
    run_lock_path: Optional[str]
    task_db_path: Optional[str]
    task_id: Optional[str]
    save_dir: Optional[str]
    ts: Optional[float]


# ── location resolution ──


def _shared_roots() -> set:
    """Directories that must never host an auto-discovered project index.

    Walking up to a stray ``.flexlock`` in ``$HOME``, the system temp dir, or
    the filesystem root would silently capture unrelated runs across projects,
    so these are skipped as index homes (an explicit ``$FLEXLOCK_INDEX`` still
    wins if the user really wants a global index).
    """
    roots = {Path(tempfile.gettempdir()).resolve()}
    try:
        roots.add(Path.home().resolve())
    except Exception:
        pass
    cur = Path(".").resolve()
    roots.add(Path(cur.anchor))  # filesystem root
    return roots


def _index_disabled_for(index_path: Path) -> bool:
    """True when the index would sit directly in a shared root with no explicit
    ``$FLEXLOCK_INDEX`` — i.e. the run isn't in a project tree, so auto-indexing
    is skipped to avoid a global index capturing unrelated runs (the glob
    fallback still applies)."""
    if os.environ.get("FLEXLOCK_INDEX"):
        return False
    host = index_path.parent.parent  # <host>/.flexlock/index.db -> <host>
    try:
        return host.resolve() in _shared_roots()
    except Exception:
        return False


def resolve_index_path(base, create_parent: bool = False) -> Path:
    """Resolve the index db path for a run/search rooted at ``base``."""
    env = os.environ.get("FLEXLOCK_INDEX")
    if env:
        p = Path(env)
    else:
        p = None
        cur = Path(base).resolve()
        skip = _shared_roots()
        # Walk up looking for an existing index to share, but never latch onto
        # a stray index in a shared root (home/tmp/fs-root).
        for candidate_dir in [cur, *cur.parents]:
            if candidate_dir in skip:
                continue
            candidate = candidate_dir / INDEX_DIRNAME / INDEX_FILENAME
            if candidate.exists():
                p = candidate
                break
        if p is None:
            p = cur / INDEX_DIRNAME / INDEX_FILENAME
    if create_parent:
        p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ── connection ──


def _connect(index_path: Path) -> sqlite3.Connection:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(index_path), timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute(_SCHEMA)
    return conn


# ── writes ──


def upsert(
    index_path: Path,
    fingerprint: str,
    location_kind: str,
    save_dir: str,
    run_lock_path: Optional[str] = None,
    task_db_path: Optional[str] = None,
    task_id: Optional[str] = None,
    status: str = STATUS_DONE,
) -> None:
    """Insert-or-replace a row keyed by fingerprint. Idempotent."""
    try:
        conn = _connect(Path(index_path))
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs "
                "(fingerprint, status, location_kind, run_lock_path, task_db_path, "
                " task_id, save_dir, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fingerprint,
                    status,
                    location_kind,
                    run_lock_path,
                    task_db_path,
                    task_id,
                    save_dir,
                    time.time(),
                ),
            )
        conn.close()
    except sqlite3.Error as e:
        # The index is a derived cache; a write failure must never break a run.
        logger.warning(f"Fingerprint index upsert failed ({index_path}): {e}")


def record_run_lock(save_dir, fingerprint: str) -> None:
    """Record a completed serial/single run (``run.lock`` location)."""
    save_dir = Path(save_dir)
    index_path = resolve_index_path(save_dir.parent)
    if _index_disabled_for(index_path):
        return
    index_path.parent.mkdir(parents=True, exist_ok=True)
    upsert(
        index_path,
        fingerprint=fingerprint,
        location_kind=LOCATION_RUN_LOCK,
        save_dir=str(save_dir),
        run_lock_path=str(save_dir / "run.lock"),
    )


def record_task(save_dir, task_db_path, task_id: str, fingerprint: str) -> None:
    """Record a completed sweep task (``(task_db, task_id)`` location)."""
    save_dir = Path(save_dir)
    index_path = resolve_index_path(save_dir.parent)
    if _index_disabled_for(index_path):
        return
    index_path.parent.mkdir(parents=True, exist_ok=True)
    upsert(
        index_path,
        fingerprint=fingerprint,
        location_kind=LOCATION_TASK,
        save_dir=str(save_dir),
        task_db_path=str(task_db_path),
        task_id=task_id,
    )


def prune(index_path: Path, fingerprint: str) -> None:
    try:
        conn = _connect(Path(index_path))
        with conn:
            conn.execute("DELETE FROM runs WHERE fingerprint=?", (fingerprint,))
        conn.close()
    except sqlite3.Error as e:
        logger.warning(f"Fingerprint index prune failed ({index_path}): {e}")


# ── reads ──


def lookup(base, fingerprint: str) -> Optional[IndexRow]:
    """Look up a done row by fingerprint, resolving the index from ``base``."""
    index_path = resolve_index_path(base)
    if _index_disabled_for(index_path) or not index_path.exists():
        return None
    try:
        conn = _connect(index_path)
        cur = conn.execute(
            "SELECT fingerprint, status, location_kind, run_lock_path, "
            "task_db_path, task_id, save_dir, ts FROM runs "
            "WHERE fingerprint=? AND status=?",
            (fingerprint, STATUS_DONE),
        )
        row = cur.fetchone()
        conn.close()
    except sqlite3.Error as e:
        logger.warning(f"Fingerprint index lookup failed ({index_path}): {e}")
        return None
    if row is None:
        return None
    return IndexRow(*row)


def verify_and_resolve(base, row: IndexRow) -> Optional[Path]:
    """Confirm the row's pointed-to run still exists and is complete.

    Returns the run's ``save_dir`` on success. On a stale pointer (deleted or
    incomplete) the row is pruned and ``None`` is returned, so the index
    self-heals to a miss.
    """
    from .run_record import RunRecord

    save_dir = Path(row.save_dir) if row.save_dir else None

    if row.location_kind == LOCATION_RUN_LOCK:
        if save_dir and RunRecord(save_dir).is_complete:
            return save_dir
    elif row.location_kind == LOCATION_TASK:
        # Task is complete iff its results.json is present (the worker writes it
        # via RunRecord.mark_complete just before recording the index row).
        if save_dir and RunRecord(save_dir).is_complete_task():
            return save_dir

    # Stale pointer — prune and report a miss.
    prune(resolve_index_path(base), row.fingerprint)
    return None


def reindex(root) -> int:
    """Backfill the index by walking ``**/run.lock`` under ``root``.

    Uses the ``fingerprint`` stored in each ``run.lock`` (written at snapshot
    time). Runs from before fingerprints were stored are skipped. Returns the
    number of rows written.
    """
    import yaml

    root = Path(root)
    count = 0
    for lock_file in root.glob("**/run.lock"):
        run_dir = lock_file.parent
        try:
            data = yaml.safe_load(lock_file.read_text())
        except Exception as e:
            logger.debug(f"reindex: skipping {lock_file}: {e}")
            continue
        if not isinstance(data, dict):
            continue
        fp = data.get("fingerprint")
        if not fp:
            continue
        if not (run_dir / "run.complete").exists():
            continue
        record_run_lock(run_dir, fp)
        count += 1
    logger.info(f"reindex: recorded {count} run(s) under {root}")
    return count
