"""Controller exclusion and queue-backed destination reservations.

No scheduler inference: pending work stays reserved until its queue is resolved.
Workers attach to existing queues independently of this controller guard.
"""
from contextlib import contextmanager, ExitStack
from functools import lru_cache
from pathlib import Path
import fcntl
import json
import sqlite3
import threading
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

# Cache only immutable, unresolved paths derived from exact task text. Queue
# status and filesystem resolution never enter this process-local cache. Large
# task documents bypass it, bounding retained text as well as entry count.
_ROW_CACHE_CHARS = 4096


def _decode_row_paths(raw, loader):
    task = yaml.load(raw, Loader=loader)
    if not hasattr(task, 'get'):
        return frozenset()
    stages = task.get('_stages_', [task])
    return frozenset(str(Path(stage['save_dir'])) for stage in stages
                     if stage.get('save_dir') and '${' not in str(stage['save_dir']))


@lru_cache(maxsize=1024)
def _cached_row_paths(raw, loader):
    return _decode_row_paths(raw, loader)


def _row_destinations(raw, resolve):
    paths = (_cached_row_paths(raw, _TASK_LOADER)
             if isinstance(raw, str) and len(raw) <= _ROW_CACHE_CHARS
             else _decode_row_paths(raw, _TASK_LOADER))
    return {resolve(path) for path in paths}


def _map_io(func, items):
    items = list(items)
    if _IO_WORKERS <= 1 or len(items) < 2:
        return [func(item) for item in items]
    from concurrent.futures import ThreadPoolExecutor
    # Context exit joins every outstanding operation, including after failure.
    with ThreadPoolExecutor(max_workers=_IO_WORKERS, thread_name_prefix='flexlock-prep') as pool:
        return list(pool.map(func, items))


def _destination_resolver():
    """Reuse shared parent resolution within one ownership scan only.

    Final components are inspected individually, including symlinks. Nothing
    survives the scan: a later check sees changes to parent and final symlinks.
    """
    parents = {}

    def resolve(value):
        path = Path(value)
        if not path.name or path.name == '..':
            return str(path.resolve())
        parent = path.parent
        if parent not in parents:
            parents[parent] = parent.resolve()
        candidate = parents[parent] / path.name
        return str(candidate.resolve() if candidate.is_symlink() else candidate)

    return resolve


def task_destinations(task, *, _resolve=None):
    """Concrete stage paths in an already compiled queue entry."""
    if not hasattr(task, 'get'):
        return set()
    stages = task.get('_stages_', [task])
    resolve = _resolve or (lambda value: str(Path(value).resolve()))
    return {resolve(stage['save_dir']) for stage in stages
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


def _open_controller_lock(path):
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return (directory / CONTROLLER_LOCK).open('a+')


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
    resolve = _destination_resolver()
    for db in databases:
        for (raw,) in _active_rows(db):
            destinations = _row_destinations(raw, resolve)
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
        ordered = sorted(locks)
        opened = []
        opened_lock = threading.Lock()

        def open_lock(path):
            stream = _open_controller_lock(path)
            with opened_lock:
                opened.append(stream)
            return stream

        try:
            streams = _map_io(open_lock, ordered)
        finally:
            # _map_io joins all opens even after an error. Register every handle
            # before propagating it, including successes after the failing item.
            for stream in opened:
                stack.enter_context(stream)
        # Only handle preparation is parallel. Acquire locks in the same global
        # order on the controller thread, then retain them through all mutations.
        for path, stream in zip(ordered, streams):
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
        resolve = _destination_resolver()
        for db in databases:
            for (raw,) in _active_rows(db):
                destinations = _row_destinations(raw, resolve)
                if (master and db.resolve() == (Path(master) / 'run.lock.tasks.db').resolve()) or destinations & products or not destinations:
                    raise FlexLockValidationError(
                        f'Destination has pending/running work in {db}; refusing before submission even with --force. '
                        'Inspect the queue/scheduler and use workers to continue that queue.')
        yield
