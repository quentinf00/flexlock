"""Data hashing utilities for FlexLock."""

import os
import sqlite3
import threading
from pathlib import Path
import xxhash
import hashlib
from joblib import Parallel, delayed
from contextlib import contextmanager

# --- Cache Configuration ---
CACHE_DIR = (
    Path(
        os.environ.get(
            "FLEXLOCK_CACHE", os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
        )
    )
    / "flexlock"
)
CACHE_DB = CACHE_DIR / "hashes.db"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DIR_FILE_LIMIT = os.environ.get("FLEXLOCK_DIR_FILE_LIMIT", 1000)

# Thread-local storage for database connections
_thread_local_conns = threading.local()


@contextmanager
def _get_db():
    """
    A thread-safe context manager for SQLite database connections.

    This function maintains a cache of connections per thread. A new connection
    is created for each unique database path and reused for subsequent calls
    with the same path within that thread.
    """
    # Use the absolute path as a reliable key for the connections dictionary.
    db_path_str = str(CACHE_DB.resolve())

    # Initialize the connections dictionary for the current thread if it doesn't exist.
    if not hasattr(_thread_local_conns, "conns"):
        _thread_local_conns.conns = {}

    # Check if a connection for this specific db_path already exists in the thread's cache.
    if db_path_str not in _thread_local_conns.conns:
        # If not, create a new connection and add it to the cache.
        try:
            c = sqlite3.connect(db_path_str, check_same_thread=False)
            # Set PRAGMA for better performance and concurrency.
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=15000")
            c.execute(
                "PRAGMA foreign_keys=ON"
            )  # Good practice to enforce foreign key constraints
            c.execute(
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
            _thread_local_conns.conns[db_path_str] = c
        except sqlite3.Error as e:
            print(f"Error connecting to database {db_path_str}: {e}")
            raise

    # Yield the connection from the thread's cache.
    try:
        yield _thread_local_conns.conns[db_path_str]
    finally:
        # Don't close the connection since we're caching it for reuse
        pass


def _hash_file_content(path):
    """Hashes a single file using XXHash."""
    hasher = xxhash.xxh64()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _get_dir_stats(path: Path, limit: int):
    """
    Walks a directory to get the file count and the latest modification time.

    If the file count exceeds the limit, it returns (limit + 1, 0) to signal
    that the directory is "large".
    """
    count = 0
    latest_mtime = path.stat().st_mtime

    for root, _, files in os.walk(path):
        count += len(files)
        if count > limit:
            return count, 0  # Exceeded limit, fallback mode

        for name in files:
            filepath = Path(root) / name
            try:
                mtime = filepath.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
            except OSError:
                # File might be a broken symlink, etc.
                pass
    return count, latest_mtime


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

    import glob
    from pathlib import Path as p_path

    # Find all files matching patterns
    files_to_hash = []
    for pattern in match_pattern:
        files_to_hash.extend(base_path.glob(pattern))

    files_to_hash = [f for f in files_to_hash if f.is_file()]

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

    file_hashes = Parallel(n_jobs=jobs)(
        delayed(_hash_file)(str(f), algorithm, chunk_size) for f in final_files
    )

    final_hasher = algorithm()
    for h in sorted(file_hashes):
        final_hasher.update(h.encode("utf-8"))

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
    Computes a hash for a file or a directory, using an SQLite cache to avoid re-computation.
    """
    path = Path(path).resolve()
    use_cache = os.environ.get("FLEXLOCK_NO_CACHE", use_cache) not in (
        "1",
        "true",
        "True",
    )
    dir_file_limit = int(
        os.environ.get("FLEXLOCK_CACHE_DIR_FILE_LIMIT", DEFAULT_DIR_FILE_LIMIT)
    )

    if use_cache:
        with _get_db() as conn:
            cursor = conn.cursor()

            if path.is_file():
                # Check cache for file
                cursor.execute(
                    "SELECT hash, mtime FROM cache WHERE path=? AND is_dir=0",
                    (str(path),)
                )
                row = cursor.fetchone()

                if row:
                    cached_hash, cached_mtime = row
                    current_mtime = path.stat().st_mtime
                    if cached_mtime == current_mtime:
                        return cached_hash
            elif path.is_dir():
                # Check cache for directory
                cursor.execute(
                    "SELECT hash, mtime, file_count, latest_mtime FROM cache WHERE path=? AND is_dir=1",
                    (str(path),)
                )
                row = cursor.fetchone()

                if row:
                    cached_hash, cached_mtime, cached_file_count, cached_latest_mtime = row
                    file_count, latest_mtime = _get_dir_stats(path, dir_file_limit)

                    if file_count > dir_file_limit:
                        # Large directory fallback
                        current_mtime = path.stat().st_mtime
                        if cached_mtime == current_mtime:
                            return cached_hash
                    else:
                        if (cached_file_count == file_count and
                            cached_latest_mtime == latest_mtime):
                            return cached_hash

    # If not in cache or cache is invalid/disabled, compute the hash
    if not path.exists():
        raise FileNotFoundError(f"The specified path does not exist: {path}")

    new_hash = None
    if path.is_file():
        new_hash = _hash_file_content(path)
    elif path.is_dir():
        new_hash = dirhash(
            path,
            match=match,
            ignore=ignore,
            jobs=jobs,
            algorithm=algorithm,
            chunk_size=chunk_size,
        )

    if new_hash is None:
        raise ValueError(f"Could not compute hash for path: {path}")

    # Update and save the cache if enabled
    if use_cache:
        with _get_db() as conn:
            cursor = conn.cursor()
            if path.is_file():
                mtime = path.stat().st_mtime
                cursor.execute(
                    "INSERT OR REPLACE INTO cache VALUES (?, ?, NULL, NULL, ?, 0)",
                    (str(path), mtime, new_hash)
                )
            elif path.is_dir():
                file_count, latest_mtime = _get_dir_stats(path, dir_file_limit)
                mtime = path.stat().st_mtime
                if file_count > dir_file_limit:
                    # For large directories, use just the directory's mtime
                    cursor.execute(
                        "INSERT OR REPLACE INTO cache VALUES (?, ?, NULL, NULL, ?, 1)",
                        (str(path), mtime, new_hash)
                    )
                else:
                    # For smaller directories, cache more detailed stats
                    cursor.execute(
                        "INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?, ?, 1)",
                        (str(path), mtime, file_count, latest_mtime, new_hash)
                    )
            conn.commit()

    return new_hash
