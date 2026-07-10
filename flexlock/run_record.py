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
