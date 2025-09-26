"""Data hashing utilities for Naga."""
import os
import json
import logging
from pathlib import Path
from dirhash import dirhash
import xxhash

log = logging.getLogger(__name__)

# --- Cache Configuration ---
CACHE_DIR = Path.home() / ".cache" / "naga"
CACHE_FILE = CACHE_DIR / "hashes.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DIR_FILE_LIMIT = 1000

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
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_cache(cache):
    """Saves the hash cache to the JSON file."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except IOError as e:
        log.warning(f"Could not save naga hash cache: {e}")


def hash_data(path, match=None, ignore=None, jobs=4, algorithm=xxhash.xxh3_64, chunk_size=2**18, use_cache=True):
    """
    Computes a hash for a file or a directory, using a cache to avoid re-computation.
    """
    path = Path(path).resolve()
    use_cache = os.environ.get("NAGA_NO_CACHE", use_cache) not in ("1", "true", "True")
    dir_file_limit = int(os.environ.get("NAGA_CACHE_DIR_FILE_LIMIT", DEFAULT_DIR_FILE_LIMIT))

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
                        "directory or set NAGA_NO_CACHE=1 to force a re-hash if inner content changed."
                    )
                else:
                    current_stats = {"file_count": file_count, "latest_mtime": latest_mtime}

            if current_stats and cached_entry.get("stats") == current_stats:
                return cached_entry["hash"]

    # If not in cache or cache is invalid/disabled, compute the hash
    if not path.exists():
        raise FileNotFoundError(f"The specified path does not exist: {path}")

    new_hash = None
    if path.is_file():
        hasher = algorithm()
        with open(path, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                hasher.update(data)
        new_hash = hasher.hexdigest()
    elif path.is_dir():
        new_hash = dirhash(
            path, match=match, ignore=ignore, jobs=jobs,
            algorithm=algorithm, chunk_size=chunk_size
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
                stats_to_cache = {"file_count": file_count, "latest_mtime": latest_mtime}
        
        cache[str(path)] = {"stats": stats_to_cache, "hash": new_hash}
        _save_cache(cache)

    return new_hash
