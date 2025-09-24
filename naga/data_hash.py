"""Data hashing utilities for Naga."""
from pathlib import Path
from dirhash import dirhash
import xxhash

def hash_data(path, match=None, ignore=None, jobs=4, algorithm=xxhash.xxh3_64, chunk_size=2**18):
    """
    Computes a hash for a file or a directory.

    Args:
        path (str or Path): The path to the file or directory to hash.
        match (list[str], optional): Glob patterns to match files in a directory.
        ignore (list[str], optional): Glob patterns to ignore files in a directory.
        jobs (int, optional): Number of parallel jobs to use for directory hashing.
        algorithm (str, optional): The hashing algorithm to use. Supports `xxhash`
                                   and algorithms compatible with `dirhash`.
        chunk_size (int, optional): The chunk size for reading files.

    Returns:
        str: The hexadecimal hash digest.
    """
    path = Path(path)
    
    # Use xxhash for single files for consistency
    if path.is_file():
        hasher = algorithm()
        with open(path, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                hasher.update(data)
        return hasher.hexdigest()

    # Use dirhash for directories
    if path.is_dir():
        return dirhash(
            path,
            match=match,
            ignore=ignore,
            jobs=jobs,
            algorithm=algorithm,
            chunk_size=chunk_size
        )
    
    raise FileNotFoundError(f"The specified path does not exist: {path}")
