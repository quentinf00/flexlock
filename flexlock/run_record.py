"""The on-disk contract for a single run directory.

``RunRecord`` is the *one* owner of the files that define a run on disk —
``run.lock`` (the snapshot written before execution), ``run.complete`` (the
success marker), and ``results.json`` (the return payload). Every writer —
the serial ``Project.submit`` path, the sweep ``worker``, and the legacy
``write_complete_marker`` helper — routes through it, so the driver and worker
are structurally identical and there is a single place to hook the
fingerprint index (see ``index.py``, wired in Phase 2.2).

All writes are atomic (temp file + ``os.replace``) so a concurrent reader
never observes a partial file.
"""

import json
import os
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from omegaconf import OmegaConf

LOCK_NAME = "run.lock"
COMPLETE_MARKER = "run.complete"
RESULTS_NAME = "results.json"
ERROR_NAME = "run.error"
COMPLETE_VERSION = 1
ERROR_VERSION = 1

# Run lifecycle states derived from what's on disk.
STATUS_DONE = "DONE"          # run.lock + run.complete
STATUS_INCOMPLETE = "INCOMPLETE"  # run.lock only (interrupted / in-flight)
STATUS_MISSING = "MISSING"    # nothing


def _atomic_write(target: Path, text: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=target.parent, delete=False) as tf:
        tf.write(text)
        tmp_name = tf.name
    os.replace(tmp_name, target)
    return target


class RunRecord:
    """Encapsulates one run directory's files and lifecycle."""

    def __init__(self, save_dir):
        self.save_dir = Path(save_dir)

    # ── paths ──
    @property
    def lock_path(self) -> Path:
        return self.save_dir / LOCK_NAME

    @property
    def complete_path(self) -> Path:
        return self.save_dir / COMPLETE_MARKER

    @property
    def results_path(self) -> Path:
        return self.save_dir / RESULTS_NAME

    @property
    def error_path(self) -> Path:
        return self.save_dir / ERROR_NAME

    # ── writers ──
    def write_lock(self, snapshot_data: dict) -> Path:
        """Write ``run.lock`` (the snapshot) atomically before execution."""
        return _atomic_write(self.lock_path, OmegaConf.to_yaml(snapshot_data))

    def write_results(self, result: Any) -> Path:
        """Write ``results.json`` with the run's return payload."""
        payload = result if isinstance(result, dict) else {"result": result}
        return _atomic_write(
            self.results_path, json.dumps(payload, indent=2, default=str)
        )

    def mark_complete(self, result: Any = None) -> Path:
        """Write ``run.complete`` after the user function returns successfully.

        A cache hit requires *both* ``run.lock`` and ``run.complete``; an
        interrupted run leaves ``run.lock`` alone and is correctly skipped.
        This is the single place the fingerprint index is refreshed (2.2).
        """
        # Success removes any stale failure record. Because every writer routes
        # through RunRecord, this single hook implements "a completed run has no
        # run.error" for the serial, sweep-worker, and legacy marker paths.
        self.clear_error()
        payload = {"ts": datetime.now().isoformat(), "version": COMPLETE_VERSION}
        if result is not None:
            payload["has_result"] = True
        return _atomic_write(self.complete_path, json.dumps(payload))

    def write_error(self, exc: BaseException, *, task_id=None, node=None) -> "Path | None":
        """Record a ``run.error`` JSON sidecar describing a failed run.

        Capturing the failure must *never* mask the original exception, so the
        entire body is defensive: any problem writing the record is logged and
        swallowed, and the caller re-raises the user's exception unchanged.
        """
        try:
            payload = {
                "version": ERROR_VERSION,
                "exc_type": type(exc).__name__,
                "exc_message": str(exc),
                "traceback": "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ),
                "timestamp": datetime.now().isoformat(),
            }
            if task_id is not None:
                payload["task_id"] = task_id
            if node is not None:
                payload["node"] = node
            return _atomic_write(self.error_path, json.dumps(payload, indent=2))
        except Exception as write_exc:  # pragma: no cover - defensive
            logger.warning(f"Could not write {ERROR_NAME} at {self.save_dir}: {write_exc}")
            return None

    def clear_error(self) -> None:
        """Remove a stale ``run.error`` if present (no-op otherwise)."""
        try:
            self.error_path.unlink(missing_ok=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Could not clear {ERROR_NAME} at {self.save_dir}: {exc}")

    # ── readers ──
    def load(self) -> Optional[dict]:
        """Return the parsed ``run.lock`` snapshot, or ``None`` if absent."""
        if not self.lock_path.exists():
            return None
        return OmegaConf.to_container(OmegaConf.load(self.lock_path), resolve=True)

    def load_results(self) -> Optional[Any]:
        """Return the parsed ``results.json`` payload, or ``None`` if absent."""
        if not self.results_path.exists():
            return None
        with open(self.results_path) as f:
            return json.load(f)

    def load_error(self) -> Optional[dict]:
        """Return the parsed ``run.error`` payload, or ``None`` if absent."""
        if not self.error_path.exists():
            return None
        try:
            with open(self.error_path) as f:
                return json.load(f)
        except Exception as exc:  # pragma: no cover - corrupt sidecar
            logger.warning(f"Could not read {ERROR_NAME} at {self.save_dir}: {exc}")
            return None

    # ── lifecycle ──
    @property
    def is_complete(self) -> bool:
        return self.lock_path.exists() and self.complete_path.exists()

    def is_complete_task(self) -> bool:
        """Completeness for a sweep-task dir, which carries ``run.complete`` and
        ``results.json`` but no ``run.lock`` (its snapshot lives in the task DB)."""
        return self.complete_path.exists() and self.results_path.exists()

    @property
    def status(self) -> str:
        if self.is_complete:
            return STATUS_DONE
        if self.lock_path.exists():
            return STATUS_INCOMPLETE
        return STATUS_MISSING


# ── effective run.lock (placeholder master → task-DB snapshot) ──
#
# A ParallelExecutor master dir gets a *placeholder* run.lock at submit time
# (``config`` holds only ``save_dir`` + ``_snapshot_``); the real, worker-side
# snapshot of each task lives in ``run.lock.tasks.db`` (``snapshot`` column).
# For a single-task HPC/isolated submission the task runs *in* the master dir,
# so that placeholder is the only run.lock of the run. Workers now overwrite
# it with the task snapshot (worker._write_owned_master_lock); the helpers
# below let readers see the real snapshot for run dirs created before that fix.

TASKS_DB_NAME = "run.lock.tasks.db"
MARKER_NAME = ".flexlock_marker"
_PLACEHOLDER_CONFIG_KEYS = {"save_dir", "_snapshot_"}


def is_placeholder_lock(lock: Any) -> bool:
    """True for a master-dir placeholder: ``config`` ⊆ {save_dir, _snapshot_}."""
    if not isinstance(lock, dict):
        return False
    cfg = lock.get("config")
    return isinstance(cfg, dict) and set(cfg) <= _PLACEHOLDER_CONFIG_KEYS


def _same_dir(a, b) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except Exception:
        return False


def merge_master_into_task_snapshot(task_snap: dict, master: Optional[dict], run_dir) -> dict:
    """Build the run.lock of a task that ran in its master dir.

    Starts from the task snapshot (resolved config, fingerprint, lineage) and
    inherits run-level metadata the worker snapshot does not carry (``note``,
    and ``repos``/``data`` when the task recorded none). A ``parent`` pointer
    to the dir's own run.lock is dropped (it would be self-referential).
    """
    out = dict(task_snap)
    master = master if isinstance(master, dict) else {}
    for key in ("note", "repos", "data"):
        if key not in out and master.get(key):
            out[key] = master[key]
    parent = out.get("parent")
    if parent and _same_dir(Path(parent).parent, run_dir):
        out.pop("parent")
    return out


def _task_snapshot_for_dir(run_dir: Path) -> Optional[dict]:
    """Read-only lookup of the task snapshot that ran *in* ``run_dir``.

    Uses the ``.flexlock_marker`` task_id when present, else the most recent
    row whose snapshot ``config.save_dir`` is ``run_dir`` (done rows first).
    Opens the DB read-only (no schema migration, no write lock).
    """
    import sqlite3

    db = run_dir / TASKS_DB_NAME
    if not db.exists():
        return None
    task_id = None
    marker = run_dir / MARKER_NAME
    if marker.exists():
        try:
            task_id = json.loads(marker.read_text()).get("task_id")
        except Exception:
            task_id = None
    try:
        conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error as exc:
        logger.warning(f"Could not open {db} read-only: {exc}")
        return None
    try:
        rows = conn.execute(
            "SELECT task_id, snapshot, status FROM tasks WHERE snapshot IS NOT NULL "
            "ORDER BY (status = 'done') DESC, ts_start DESC"
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning(f"Could not read {db}: {exc}")
        return None
    finally:
        conn.close()
    candidates = []
    for tid, snap_text, _status in rows:
        try:
            snap = json.loads(snap_text)
        except Exception:
            continue
        if task_id is not None and tid == task_id:
            return snap
        save_dir = (snap.get("config") or {}).get("save_dir")
        if save_dir is not None and _same_dir(save_dir, run_dir):
            candidates.append(snap)
    return candidates[0] if candidates else None


def load_lock_data(run_dir) -> Optional[dict]:
    """Side-effect-free *effective* run.lock of ``run_dir`` (or ``None``).

    Parses ``run.lock`` with ``yaml.safe_load`` (no resolvers fire). When it is
    a master placeholder and the dir's task DB holds the snapshot of a task
    that ran in this very dir (single-task HPC/isolated submission), returns
    that snapshot merged with the master's run-level metadata instead. Sweep
    masters (tasks in sub-dirs) keep their placeholder: there is no single
    config to show for them.
    """
    import yaml

    run_dir = Path(run_dir)
    lock_path = run_dir / LOCK_NAME
    if not lock_path.exists():
        return None
    with open(lock_path) as f:
        lock = yaml.safe_load(f)
    if not is_placeholder_lock(lock):
        return lock
    snap = _task_snapshot_for_dir(run_dir)
    if snap is None:
        return lock
    logger.debug(f"{lock_path} is a placeholder; using the task snapshot from {TASKS_DB_NAME}")
    return merge_master_into_task_snapshot(snap, lock, run_dir)


def materialize_lock(run_dir, backup: bool = True) -> bool:
    """Rewrite a placeholder ``run.lock`` with its effective (task-DB) content.

    One-off repair for run dirs created before workers finalized run.lock.
    Keeps the placeholder as ``run.lock.placeholder.bak`` when ``backup``.
    Returns True when the file was rewritten.
    """
    import yaml

    run_dir = Path(run_dir)
    lock_path = run_dir / LOCK_NAME
    if not lock_path.exists():
        return False
    with open(lock_path) as f:
        raw = yaml.safe_load(f)
    if not is_placeholder_lock(raw):
        return False
    effective = load_lock_data(run_dir)
    if effective is None or is_placeholder_lock(effective):
        return False
    if backup:
        _atomic_write(run_dir / "run.lock.placeholder.bak", lock_path.read_text())
    RunRecord(run_dir).write_lock(effective)
    return True
