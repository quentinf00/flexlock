"""Data hashing utilities for FlexLock."""

import os
import json
import logging
from pathlib import Path
import xxhash
import hashlib
import os
from pathlib import Path
from glob import glob
from joblib import Parallel, delayed

log = logging.getLogger(__name__)

# --- Cache Configuration ---
CACHE_DIR = Path(
        os.environ.get(
            "FLEXLOCK_CACHE",
            os.environ.get(
                "XDG_CACHE_HOME", Path.home() / ".cache" )
        )
) / "flexlock"
CACHE_FILE = CACHE_DIR / "hashes.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DIR_FILE_LIMIT = os.environ.get("FLEXLOCK_DIR_FILE_LIMIT", 1000)

# --- Helper Functions ---


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
            filepath = os.path.join(root, name)
            try:
                mtime = os.path.getmtime(filepath)
                if mtime > latest_mtime:
                    latest_mtime = mtime
            except OSError:
                # File might be a broken symlink, etc.
                pass
    return count, latest_mtime


def _load_cache():
    """Loads the hash cache from the JSON file."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_cache(cache):
    """Saves the hash cache to the JSON file."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except IOError as e:
        log.warning(f"Could not save flexlock hash cache: {e}")


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

    included_files_set = set()
    for pattern in match_pattern:
        for f in base_path.glob(pattern):
            if f.is_file():
                included_files_set.add(f)

    excluded_files_set = set()
    for pattern in ignore_patterns:
        for f in base_path.glob(pattern):
            if f.is_file():
                excluded_files_set.add(f)

    files_to_hash = sorted(list(included_files_set - excluded_files_set))

    if not files_to_hash:
        return algorithm().hexdigest()

    file_hashes = Parallel(n_jobs=jobs)(
        delayed(_hash_file)(str(f), algorithm, chunk_size) for f in files_to_hash
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
    algorithm=xxhash.xxh3_64,
    chunk_size=2**18,
    use_cache=True,
):
    """
    Computes a hash for a file or a directory, using a cache to avoid re-computation.
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

    cache = {}
    if use_cache:
        cache = _load_cache()
        path_str = str(path)

        if path_str in cache:
            cached_entry = cache[path_str]
            current_stats = None

            if path.is_file():
                current_stats = {"mtime": path.stat().st_mtime}
            elif path.is_dir():
                file_count, latest_mtime = _get_dir_stats(path, dir_file_limit)
                if file_count > dir_file_limit:
                    # Large directory fallback
                    current_stats = {"mtime": path.stat().st_mtime}
                    log.warning(
                        f"Directory '{path_str}' has over {dir_file_limit} files. "
                        "Falling back to less accurate timestamp caching. Use `touch` on the "
                        "directory or set FLEXLOCK_NO_CACHE=1 to force a re-hash if inner content changed."
                    )
                else:
                    current_stats = {
                        "file_count": file_count,
                        "latest_mtime": latest_mtime,
                    }

            if current_stats and cached_entry.get("stats") == current_stats:
                return cached_entry["hash"]

    # If not in cache or cache is invalid/disabled, compute the hash
    if not path.exists():
        raise FileNotFoundError(f"The specified path does not exist: {path}")

    new_hash = None
    if path.is_file():
        new_hash = _hash_file(path, algorithm, chunk_size)
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
        stats_to_cache = None
        if path.is_file():
            stats_to_cache = {"mtime": path.stat().st_mtime}
        elif path.is_dir():
            file_count, latest_mtime = _get_dir_stats(path, dir_file_limit)
            if file_count > dir_file_limit:
                stats_to_cache = {"mtime": path.stat().st_mtime}
            else:
                stats_to_cache = {
                    "file_count": file_count,
                    "latest_mtime": latest_mtime,
                }

        cache[str(path)] = {"stats": stats_to_cache, "hash": new_hash}
        _save_cache(cache)

    return new_hash


if __name__ == "__main__":
    # --- Example Usage ---

    # 1. Create some dummy files and directories for testing
    test_dir = Path("./test_dir_for_dirhash")
    test_dir.mkdir(exist_ok=True)
    (test_dir / "file1.txt").write_text("content of file 1")
    (test_dir / "file2.py").write_text("import os\nprint('hello')")
    (test_dir / "sub_dir").mkdir(exist_ok=True)
    (test_dir / "sub_dir" / "file3.txt").write_text("another file")
    (test_dir / "sub_dir" / "ignore_me.log").write_text("log content")
    (test_dir / "temp_file.tmp").write_text("temporary data")
    (test_dir / ".gitignore").write_text(
        "*.tmp\n*.log"
    )  # This file itself can be ignored or included

    print(f"Hashing directory: {test_dir.resolve()}")

    # Basic hash of all files
    hash1 = dirhash(test_dir)
    print(f"Default hash (all files, md5): {hash1}")

    # Hash with specific algorithm
    hash2 = dirhash(test_dir, algorithm=hashlib.sha256)
    print(f"SHA256 hash (all files): {hash2}")

    # Hash ignoring certain files
    hash3 = dirhash(test_dir, ignore=["*.log", "*.tmp"])
    print(f"Hash ignoring .log and .tmp files: {hash3}")

    # Hash matching only .txt files
    hash4 = dirhash(test_dir, match="**/*.txt")
    print(f"Hash only .txt files: {hash4}")

    # Hash with multiple match patterns
    hash5 = dirhash(test_dir, match=["*.txt", "**/*.py"])
    print(f"Hash .txt and .py files: {hash5}")

    # Hash with multiple ignore patterns
    hash6 = dirhash(test_dir, ignore=["*.tmp", "sub_dir/*"])
    print(f"Hash ignoring .tmp and contents of sub_dir: {hash6}")

    # Demonstrate changes affecting the hash
    (test_dir / "file1.txt").write_text("updated content of file 1")
    hash1_updated = dirhash(test_dir)
    print(f"Updated default hash (file1 changed): {hash1_updated}")
    print(f"Hashes are different after change: {hash1 != hash1_updated}")

    # Clean up test directory
    import shutil

    shutil.rmtree(test_dir)
    print(f"\nCleaned up {test_dir}")
