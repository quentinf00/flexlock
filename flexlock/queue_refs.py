"""Read existing queue locators without changing their on-disk formats."""
import json
from pathlib import Path

from .exceptions import FlexLockValidationError

QUEUE_POINTER = '.flexlock-queue.json'
MARKER_NAME = '.flexlock_marker'
TASKS_DB_NAME = 'run.lock.tasks.db'


def _read_json(path, *, strict=False):
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError('queue reference must be an object')
        return value
    except FileNotFoundError as exc:
        if strict and path.is_symlink():
            raise FlexLockValidationError(f'Unreadable reservation {path}') from exc
        return None
    except (OSError, ValueError) as exc:
        if strict:
            raise FlexLockValidationError(f'Unreadable reservation {path}') from exc
        return None


def read_marker(run_dir, *, strict=False):
    return _read_json(Path(run_dir)/MARKER_NAME, strict=strict)


def marker_db(run_dir, marker):
    """Legacy marker paths are relative to the receipt directory's parent."""
    db = Path(marker.get('db', ''))
    return db if db.is_absolute() else Path(run_dir).parent/db


def referenced_databases(run_dir):
    """Current reservations and legacy receipts, with canonical DB identities.

    A missing reservation DB is ambiguous and rejected. A marker-only archived
    receipt may retain a standalone run.lock after its old DB has been removed;
    keep that historical behavior. Malformed locators fail closed for ownership.
    """
    directory = Path(run_dir)
    databases = set()
    pointer = _read_json(directory/QUEUE_POINTER, strict=True)
    if pointer is not None:
        value = pointer.get('task_db')
        if not isinstance(value, str) or not value:
            raise FlexLockValidationError(f'Unreadable reservation {directory/QUEUE_POINTER}')
        db = Path(value).resolve()
        if not db.exists():
            raise FlexLockValidationError(f'Destination reservation references missing queue {db}; ownership is unknown')
        databases.add(db)
    marker = read_marker(directory, strict=True)
    if marker is not None:
        value = marker.get('db')
        if not isinstance(value, str) or not value:
            raise FlexLockValidationError(f'Unreadable reservation {directory/MARKER_NAME}')
        databases.add(marker_db(directory, marker).resolve())
    return databases


def ancestor_candidates(directories):
    """Deduplicated own/ancestor DB paths for already canonical directories.

    This inspects fixed queue filenames along selected paths, not cache discovery
    or a filesystem tree scan. Callers decide how to probe the candidates.
    """
    return {parent/TASKS_DB_NAME for directory in directories
            for parent in (Path(directory), *Path(directory).parents)}
