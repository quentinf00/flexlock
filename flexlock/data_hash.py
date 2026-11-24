"""Data hashing utilities for FlexLock."""

import os
import sqlite3
import fcntl
import tempfile
from pathlib import Path
import xxhash
import hashlib
from joblib import Parallel, delayed
from contextlib import closing, contextmanager
from loguru import logger

from . import config

# Hash-format version. Bump when the on-disk hash algorithm changes so stale
# rows in an old cache file are never returned as valid hits. v2: dirhash now
# folds each file's relative path into the digest (previously content-only).
HASH_VERSION = 2

# --- Cache Configuration ---
CACHE_DIR = (
    Path(
        os.environ.get(
            "FLEXLOCK_CACHE", os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
        )
    )
    / "flexlock"
)
CACHE_DB = CACHE_DIR / f"hashes_v{HASH_VERSION}.db"


@contextmanager
def _get_db():
    """Open the cache with a rollback journal and close it before recovery."""
    with closing(sqlite3.connect(CACHE_DB, timeout=1)) as conn, conn:
        (mode,) = conn.execute("PRAGMA journal_mode=DELETE").fetchone()
        if mode != "delete":
            raise sqlite3.OperationalError(f"Hash cache uses journal mode {mode}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                path TEXT PRIMARY KEY,
                mtime REAL,
                file_count INTEGER,
                latest_mtime REAL,
                hash TEXT,
                is_dir INTEGER
            )
            """
        )
        yield conn


def _quarantine_cache():
    """Preserve the damaged database and any journal files together."""
    quarantine = Path(tempfile.mkdtemp(prefix=f"{CACHE_DB.name}.corrupt-", dir=CACHE_DB.parent))
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = Path(f"{CACHE_DB}{suffix}")
        if path.exists():
            path.rename(quarantine / path.name)
    logger.warning(f"Moved damaged hash cache to {quarantine}")


def _cache_execute(sql, params):
    """Run a cache operation, rebuilding once on corruption."""
    try:
        CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        # Hold the same lock for access and recovery so no other updated client
        # can open a partially quarantined database or keep using its old inode.
        with CACHE_DB.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not CACHE_DB.exists() and any(
                Path(f"{CACHE_DB}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal")
            ):
                _quarantine_cache()
            try:
                with _get_db() as conn:
                    return conn.execute(sql, params).fetchone()
            except sqlite3.DatabaseError as exc:
                code = getattr(exc, "sqlite_errorcode", 0) & 0xff
                if code not in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                    raise
                _quarantine_cache()
                with _get_db() as conn:
                    return conn.execute(sql, params).fetchone()
    except BlockingIOError:
        # Cache contention is cheaper to bypass than to block a run on it.
        return None
    except (OSError, sqlite3.Error) as exc:
        logger.warning(f"Skipping hash cache {CACHE_DB}: {exc}")
        return None


def _hash_file_content(path):
    """Hashes a single file using XXHash."""
    hasher = xxhash.xxh64()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def dirhash(
    path, match=None, ignore=None, jobs=1, algorithm=hashlib.md5, chunk_size=65536
):
    """
    Computes a hash of the directory content using pathlib.glob for filtering.
    """
    base_path = Path(path)
    if not base_path.is_dir():
        raise ValueError(f"'{path}' is not a valid directory.")

    # Default match to all files recursively if not specified
    match_pattern = match if match is not None else "**/*"
    if isinstance(match_pattern, str):
        match_pattern = [match_pattern]

    ignore_patterns = ignore if ignore is not None else []
    if isinstance(ignore_patterns, str):
        ignore_patterns = [ignore_patterns]

    # Find all files matching patterns
    files_to_hash = []
    for pattern in match_pattern:
        files_to_hash.extend(base_path.glob(pattern))

    files_to_hash = sorted({f for f in files_to_hash if f.is_file()})

    # Apply ignore patterns
    final_files = []
    for f in files_to_hash:
        should_ignore = False
        for pattern in ignore_patterns:
            if f.match(pattern):
                should_ignore = True
                break
        if not should_ignore:
            final_files.append(f)

    if not final_files:
        return algorithm().hexdigest()

    def _hash_file(filepath, algorithm, chunk_size):
        """Hashes a single file."""
        hasher = algorithm()
        with open(filepath, "rb") as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                hasher.update(data)
        return hasher.hexdigest()

    content_hashes = Parallel(n_jobs=jobs)(
        delayed(_hash_file)(str(f), algorithm, chunk_size) for f in final_files
    )

    # Fold the file's path into the digest so that two directories with
    # identical file *contents* under different names hash differently, and so
    # that swapping contents between two paths changes the hash.
    entries = [
        f"{f.relative_to(base_path).as_posix()}\0{h}"
        for f, h in zip(final_files, content_hashes)
    ]

    final_hasher = algorithm()
    for entry in sorted(entries):
        final_hasher.update(entry.encode("utf-8"))

    return final_hasher.hexdigest()


def hash_data(
    path,
    match=None,
    ignore=None,
    jobs=4,
    algorithm=xxhash.xxh64,
    chunk_size=2**18,
    use_cache=True,
):
    """
    Hash selected file paths and bytes. Directories are always read in full.

    Only single files use the legacy mtime cache. Directory aggregate metadata
    cannot establish unchanged nested content or distinguish selection filters.
    """
    path = Path(path).resolve()
    # Honour the ``use_cache`` argument; the env var can only *force* caching
    # off (it never re-enables a cache the caller explicitly disabled).
    use_cache = use_cache and not config.get_env_bool("FLEXLOCK_NO_CACHE", False)
    # Never reuse an aggregate directory hash based on root mtime, file count
    # or maximum child mtime. These miss edits, renames and filtered selections.
    if path.is_dir():
        return dirhash(path, match=match, ignore=ignore, jobs=jobs,
                       algorithm=algorithm, chunk_size=chunk_size)

    if not path.exists():
        raise FileNotFoundError(f"The specified path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Could not compute hash for path: {path}")

    mtime = path.stat().st_mtime
    if use_cache:
        row = _cache_execute(
            "SELECT hash FROM cache WHERE path=? AND mtime=? AND is_dir=0",
            (str(path), mtime),
        )
        if row is not None:
            return row[0]

    new_hash = _hash_file_content(path)
    if use_cache:
        _cache_execute(
            "INSERT OR REPLACE INTO cache VALUES (?, ?, NULL, NULL, ?, 0)",
            (str(path), mtime, new_hash),
        )
    return new_hash
