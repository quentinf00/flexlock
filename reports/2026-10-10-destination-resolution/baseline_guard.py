"""Controller exclusion and queue-backed destination reservations.

No scheduler inference: pending work stays reserved until its queue is resolved.
Workers attach to existing queues independently of this controller guard.
"""
from contextlib import contextmanager, ExitStack
from pathlib import Path
import fcntl
import json
import sqlite3
import yaml

from .exceptions import FlexLockValidationError
from .queue_refs import QUEUE_POINTER, referenced_databases, ancestor_candidates

CONTROLLER_LOCK = '.flexlock-controller.lock'

# Internal bounded I/O only; resolver compilation and SQLite writes never enter
# this pool. Two workers matched four's median with less variation in the pilot.
_IO_WORKERS = 2

# Ownership needs plain YAML values, not OmegaConf construction. Preserve safe
# YAML semantics (including timestamps) and retain the pure-Python fallback.
_TASK_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)


def _map_io(func, items):
    items = list(items)
    if _IO_WORKERS <= 1 or len(items) < 2:
        return [func(item) for item in items]
    from concurrent.futures import ThreadPoolExecutor
    # Context exit joins every outstanding operation, including after failure.
    with ThreadPoolExecutor(max_workers=_IO_WORKERS, thread_name_prefix='flexlock-prep') as pool:
        return list(pool.map(func, items))


def task_destinations(task):
    """Concrete stage paths in an already compiled queue entry."""
    if not hasattr(task, 'get'):
        return set()
    stages = task.get('_stages_', [task])
    return {str(Path(stage['save_dir']).resolve()) for stage in stages
            if stage.get('save_dir') and '${' not in str(stage['save_dir'])}


def reserve_queue(paths, db_path):
    """Point products at their authoritative queue before scheduler submission."""
    payload = json.dumps({'task_db': str(Path(db_path).resolve())})
    # Aliases must not race on one product's temporary pointer file.
    directories = sorted({Path(path).resolve() for path in paths})
    _map_io(lambda directory: _write_reservation(directory, payload), directories)


def _write_reservation(directory, payload):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / QUEUE_POINTER
    temporary = target.with_suffix('.tmp')
    temporary.write_text(payload)
    temporary.replace(target)


def _product_databases(path):
    """Read one locked product's current/legacy pointers; no resolver mutation."""
    return referenced_databases(path)


def _existing_database(path):
    return path if path.exists() else None


def _active_rows(db):
    # Do not open/create a task DB through the mutating taskdb connection cache.
    if not db.exists():
        return []
    try:
        with sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True) as conn:
            return conn.execute("SELECT task_info FROM tasks WHERE status IN ('pending', 'running')").fetchall()
    except sqlite3.Error as exc:
        raise FlexLockValidationError(f'Cannot establish destination ownership from {db}: {exc}') from exc


def has_active_destination(path):
    """Read a selected producer's queue reservation, without creating a DB.

    A queued placeholder is promised work, not a finished producer binding.
    Include historical ancestor queues even when a stale explicit pointer names
    a different terminal queue. No scheduler or cache search is involved.
    """
    directory = Path(path).resolve()
    databases = _product_databases(directory)
    databases.update(db for candidate in ancestor_candidates([directory])
                     if (db := _existing_database(candidate)) is not None)
    for db in databases:
        for (raw,) in _active_rows(db):
            destinations = task_destinations(yaml.load(raw, Loader=_TASK_LOADER))
            if not destinations or str(directory) in destinations:
                return True
    return False


@contextmanager
def guard_destinations(paths, db_dir=None):
    """Hold controller locks across preflight, mutations and launch/execution.

    A pending/running queue row prevents a new controller from reusing its product
    directory, even before run.lock exists. Force never bypasses this reservation.
    """
    products = {str(Path(path).resolve()) for path in paths}
    master = str(Path(db_dir).resolve()) if db_dir is not None else None
    locks = products | ({master} if master else set())
    with ExitStack() as stack:
        for path in sorted(locks):
            directory = Path(path)
            directory.mkdir(parents=True, exist_ok=True)
            stream = stack.enter_context((directory / CONTROLLER_LOCK).open('a+'))
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise FlexLockValidationError(f'Destination {path} is owned by another controller; refusing before submission.') from exc
        databases = {Path(master) / 'run.lock.tasks.db'} if master else set()
        for found in _map_io(_product_databases, sorted(products)):
            databases.update(found)
        # Shared ancestors need one probe per guarded invocation, rather than
        # one per product. Keep own-directory and historical ancestor queues.
        ancestors = ancestor_candidates(products)
        databases.update(path for path in _map_io(_existing_database, sorted(ancestors))
                         if path is not None)
        for db in databases:
            for (raw,) in _active_rows(db):
                task = yaml.load(raw, Loader=_TASK_LOADER)
                destinations = task_destinations(task)
                if (master and db.resolve() == (Path(master) / 'run.lock.tasks.db').resolve()) or destinations & products or not destinations:
                    raise FlexLockValidationError(
                        f'Destination has pending/running work in {db}; refusing before submission even with --force. '
                        'Inspect the queue/scheduler and use workers to continue that queue.')
        yield
