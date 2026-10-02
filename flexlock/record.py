"""One reader for run records, wherever they live.

A run's record (the ``run.lock`` content: config, repos, env, data,
fingerprint, lineage, ...) lives in one of three places:

* ``<save_dir>/run.lock``: serial runs, and sweep tasks run with
  ``task_record="dir"`` (the default). A task's file carries ``task_id``.
* the task DB (``<sweep_root>/run.lock.tasks.db``): sweep tasks run with
  ``task_record="db"``. The task dir holds only a ``.flexlock_marker``
  pointing at the DB row, and the row stores a *delta*: the code state
  (``repos``/``env``) and ``note`` live in the sweep master's ``run.lock``.
* a sweep master ``run.lock`` next to ``run.lock.tasks.db``: a stub
  describing the whole sweep, not a single run.

:func:`load_record` hides this: given a run directory it returns the
complete record, materializing DB deltas with their master. Every consumer
(cache fallback, diff, lineage, ``${run_lock:}``, show/graph, reindex,
export) goes through it.

Everything here is side-effect free: files are read with ``yaml.safe_load``
and interpolations are never resolved.
"""

import json
from pathlib import Path
from typing import Iterator, Optional

import yaml

LOCK_NAME = "run.lock"
MARKER_NAME = ".flexlock_marker"
TASKS_DB_NAME = "run.lock.tasks.db"

# Master fields a task delta inherits when materialized.
_INHERITED = ("repos", "env", "note")


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps timestamps as strings (as OmegaConf.load does).

    Plain safe_load turns an unquoted ISO timestamp into ``datetime``, which
    OmegaConf rejects when the record is later wrapped (e.g. into lineage).
    """


_Loader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def read_lock(run_dir) -> Optional[dict]:
    """Parse ``run_dir/run.lock``, or ``None`` if absent or unreadable."""
    lock = Path(run_dir) / LOCK_NAME
    try:
        with open(lock) as f:
            data = yaml.load(f, Loader=_Loader)
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def read_marker(run_dir) -> Optional[dict]:
    """Parse ``run_dir/.flexlock_marker``, or ``None``."""
    try:
        return json.loads((Path(run_dir) / MARKER_NAME).read_text())
    except (OSError, ValueError):
        return None


def marker_db(run_dir, marker: dict) -> Path:
    """Task DB path from a marker (relative paths are relative to the parent dir)."""
    db = Path(marker.get("db", ""))
    if not db.is_absolute():
        db = Path(run_dir).parent / db
    return db


def is_run_dir(path) -> bool:
    """True if ``path`` holds a run record of any kind."""
    p = Path(path)
    return (p / LOCK_NAME).exists() or (p / MARKER_NAME).exists()


def materialize(task_snapshot: dict, master: Optional[dict]) -> dict:
    """A task delta completed with the fields it inherits from its master."""
    record = dict(task_snapshot)
    if "stages" in record:
        record["stages"] = {
            path: materialize(stage, master)
            for path, stage in record["stages"].items()
        }
    for key in _INHERITED:
        if record.get(key) is None and master and master.get(key) is not None:
            record[key] = master[key]
    return record


def _record_from_db(run_dir, marker: dict) -> Optional[dict]:
    from .taskdb import get_task_snapshot

    db = marker_db(run_dir, marker)
    task_id = marker.get("task_id")
    if not task_id or not db.exists():
        return None
    snap = get_task_snapshot(db, task_id)
    if not snap:
        return None
    if "stages" in snap:
        snap = snap["stages"].get(str(Path(run_dir).resolve()))
        if not snap:
            return None
    return materialize(snap, read_lock(db.parent))


def is_task_record(lock: Optional[dict]) -> bool:
    """True for a ``run.lock`` written by a worker for one task (dir mode)."""
    return bool(lock) and "task_id" in lock


def load_record(run_dir) -> Optional[dict]:
    """The complete record for ``run_dir``, or ``None`` if it has none.

    Precedence: a ``run.lock`` that describes this run (a task record, or any
    lock without a task DB beside it) → the task DB row named by
    ``.flexlock_marker`` (materialized with its master) → whatever
    ``run.lock`` is there (a sweep master).
    """
    run_dir = Path(run_dir)
    lock = read_lock(run_dir)
    if lock is not None and (
        is_task_record(lock) or not (run_dir / TASKS_DB_NAME).exists()
    ):
        return lock
    marker = read_marker(run_dir)
    if marker is not None:
        record = _record_from_db(run_dir, marker)
        if record is not None:
            return record
    if lock is not None and (run_dir / TASKS_DB_NAME).exists():
        from .run_record import is_placeholder_lock, _task_snapshot_for_dir

        if is_placeholder_lock(lock):
            snapshot = _task_snapshot_for_dir(run_dir)
            if snapshot is not None:
                record = materialize(snapshot, lock)
                parent = record.get("parent")
                if parent and Path(parent).parent.resolve() == run_dir.resolve():
                    record.pop("parent")
                return record
    return lock


def iter_run_dirs(root) -> Iterator[Path]:
    """Every directory under ``root`` holding a ``run.lock`` or a marker, once."""
    root = Path(root)
    dirs = {p.parent for p in root.rglob(LOCK_NAME)}
    dirs |= {p.parent for p in root.rglob(MARKER_NAME)}
    yield from sorted(dirs)


def find_run_dir(start_path) -> Optional[str]:
    """Walk up from ``start_path`` to the nearest run directory."""
    p = Path(start_path)
    if p.is_file():
        p = p.parent
    while p != p.parent:
        if is_run_dir(p):
            return str(p)
        p = p.parent
    return None
