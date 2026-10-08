"""One reader for run records, wherever they live.

A run's record (the ``run.lock`` content: config, repos, env, data,
fingerprint, lineage, ...) lives in one of three places:

* ``<save_dir>/run.lock``: serial runs, and sweep tasks run with
  ``task_record="dir"`` (the default). A task's file carries ``task_id``.
* the task DB (``<sweep_root>/run.lock.tasks.db``): sweep tasks run with
  ``task_record="db"``. The task dir holds only a ``.flexlock_marker``
  pointing at the DB row. New rows retain their own code state and note;
  historical delta rows inherit these fields from the recorded master.
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


class _Loader(getattr(yaml, 'CSafeLoader', yaml.SafeLoader)):
    """SafeLoader that keeps timestamps as strings (as OmegaConf.load does).

    Plain safe_load turns an unquoted ISO timestamp into ``datetime``, which
    OmegaConf rejects when the record is later wrapped (e.g. into lineage).
    Use LibYAML when available, with the same safe constructors and a Python
    fallback; no record format or additional dependency is required.
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
    for key in _INHERITED if record.get('record_version', 1) < 2 else ():
        if record.get(key) is None and master and master.get(key) is not None:
            record[key] = master[key]
    return record


def _record_from_db(run_dir, marker: dict) -> Optional[dict]:
    db = marker_db(run_dir, marker)
    task_id = marker.get("task_id")
    if not task_id or not db.exists():
        return None
    item = load_task_record(db, task_id)
    snap = item.get('snapshot') if item else None
    if not snap:
        return None
    if "stages" in snap:
        stages = snap['stages']
        snap = stages.get(str(Path(run_dir).resolve())) or next(
            (s for s in stages.values() if s.get('record_dir') == str(Path(run_dir).resolve())), None)
        if not snap:
            return None
    return materialize(snap, read_lock(db.parent))


def list_task_records(db_path, tags=None, check_outputs=False, *, _task_id=None) -> list:
    """Read logical items without database migration or changing lifecycle state.

    The database is authoritative for status/result; directories carry artifact
    contracts. Unknown fields in historical schemas remain absent/None.
    """
    return _list_task_records(db_path, tags, check_outputs, _task_id=_task_id)


def _list_task_records(db_path, tags=None, check_outputs=False, *, _task_id=None,
                       task_ids=None, statuses=None) -> list:
    """Internal selection before decoding; public records keep their full shape."""
    import sqlite3
    from urllib.parse import quote

    db = Path(db_path).resolve()
    with sqlite3.connect(f'file:{quote(str(db))}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute('PRAGMA table_info(tasks)')}
        if 'task_id' not in columns:
            raise ValueError(f'No task table in {db}')
        clauses, params = [], []
        if _task_id is not None:
            clauses.append('task_id=?')
            params.append(_task_id)
        if statuses is not None:
            statuses = tuple(statuses)
            if not statuses:
                return []
            clauses.append('status IN (' + ','.join('?' for _ in statuses) + ')')
            params.extend(statuses)
        sql = 'SELECT * FROM tasks' + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY task_id'
        records = [dict(row) for row in conn.execute(sql, params)]
    if not records:
        return []
    master = read_lock(db.parent) or {}
    selected = {tags} if isinstance(tags, str) else set(tags or [])
    requested = set(task_ids) if task_ids is not None else None
    result = []
    for row in records:
        if requested is not None and row['task_id'] not in requested:
            continue
        if selected and row.get('tag') not in selected:
            continue
        task = yaml.load(row.get('task_info') or '{}', Loader=_Loader)
        payload = yaml.load(row['result_info'], Loader=_Loader) if row.get('result_info') is not None else None
        snapshot = json.loads(row['snapshot']) if row.get('snapshot') else {}
        snapshot = materialize(snapshot, master)
        cfg = snapshot.get('config') or (task if isinstance(task, dict) else {})
        save_dir = cfg.get('save_dir')
        record_dir = snapshot.get('record_dir') or save_dir
        entry = dict(task_id=row['task_id'], database=str(db), tag=row.get('tag'),
                     status=row['status'], result=payload, error=row.get('error'),
                     node=row.get('node'), job_id=row.get('job_id'),
                     ts_start=row.get('ts_start'), ts_end=row.get('ts_end'),
                     save_dir=save_dir, record_dir=record_dir, config=cfg,
                     task=task, snapshot=snapshot,
                     task_record=snapshot.get('task_record', master.get('task_record', 'legacy')),
                     artifact_health='not-checked')
        if check_outputs and row['status'] == 'done':
            from .outputs import validate_outputs
            stages = snapshot.get('stages', {}).values() if 'stages' in snapshot else [snapshot]
            try:
                declared = False
                for stage in stages:
                    stage_cfg = stage.get('config') or cfg
                    declared |= bool(stage_cfg.get('_outputs_'))
                    validate_outputs(stage_cfg, record_dir=stage.get('record_dir'))
                entry['artifact_health'] = 'valid' if declared else 'undeclared'
            except Exception as exc:
                entry.update(artifact_health='invalid', artifact_error=str(exc))
        result.append(entry)
    return result


def load_task_record(db_path, task_id) -> Optional[dict]:
    """Read a specific logical item, including shared-root items, by DB identity."""
    return next(iter(list_task_records(db_path, _task_id=task_id)), None)


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
