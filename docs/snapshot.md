# `snapshot`: Experiment Tracking

The `snapshot` function is the cornerstone of reproducibility in FlexLock. It creates a `run.lock` file, which is a comprehensive and immutable receipt of your experiment. This file captures everything needed to reproduce your run: the exact configuration, the version of your code, the hashes of your data, and links to previous stages.

## Basic Usage

Here's how to integrate `snapshot` into a simple processing script:

```python
from pathlib import Path
from flexlock import snapshot

class Config:
    param = 1
    input_path = 'data/input.csv'
    save_dir = 'results/process'

def main(cfg: Config = Config()):
    # --- Your core logic runs here ---
    # For example, processing data and saving results.
    output_path = Path(cfg.save_dir) / 'output.txt'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("results")
    # --- Core logic ends ---

    # Create the snapshot after the process has successfully completed.
    snapshot(
        config=cfg,
        snapshot_path=Path(cfg.save_dir) / 'run.lock', # (default if save_dir is in config)
        merge=True, # Merge with existing run.lock if it exists
        commit=True, # Commit changes to git before snapshotting
        commit_branch="flexlock-run-logs", # Branch to commit to
        commit_message="FlexLock: Auto-snapshot", # Commit message
        mlflowlink=False, # Log to MLflow
        resolve=True, # Resolve OmegaConf config before snapshotting
        prevs_from_data=True, # Automatically add data paths to prevs
        force=False, # Force new snapshot even if run.lock exists
    )

if __name__ == '__main__':
    main()
```

Running this script will create a `run.lock` file in `results/process/`. This file is a YAML that contains the resolved configuration used for the run.

## Tracking Code Version

To ensure that you can always trace your results back to the exact code that produced them, `snapshot` can track the Git commit of your repositories.

```python
snapshot(
    config=cfg,
    repos=['.']  # Tracks the Git commit of the current directory
)
```

If your project involves multiple repositories, you can provide paths to each of them:

```python
snapshot(
    config=cfg,
    repos={
        'main_project': '.',
        'shared_library': '../libs/my_lib'
    }
)
```

## Tracking Data

To ensure data provenance, `snapshot` can hash your input files and directories.

```python
snapshot(
    config=cfg,
    repos=['.'],
    data=[cfg.input_path]  # Hashes the file at cfg.input_path
)
```

You can also provide a dictionary to give meaningful names to your data dependencies:

```python
snapshot(
    config=cfg,
    repos=['.'],
    data={
        'raw_dataset': cfg.input_path,
        'validation_set': 'data/validation.csv'
    }
)
```

## Tracking Previous Stages

Complex workflows often involve multiple stages (e.g., preprocessing, training, evaluation). `snapshot` allows you to link a run to its predecessors by embedding their `run.lock` files.

```python
snapshot(
    config=cfg,
    repos=['.'],
    data=[cfg.input_path],
    prevs=[Path(cfg.input_path).parent] # Path to the directory of the previous stage
)
```

This will look for a `run.lock` file in the parent directory of `cfg.input_path` and embed it in the new `run.lock`. This creates a complete, traceable graph of your experiment pipeline.

---

## Data Hashing System

FlexLock uses content-based hashing to track data dependencies and ensure reproducibility. Understanding how this system works helps you use it effectively and troubleshoot issues.

### The `hash_data()` Function

You can compute hashes directly using the `hash_data()` function, which is exposed in FlexLock's public API:

```python
from flexlock import hash_data

# Hash a single file
file_hash = hash_data("data/input.csv")
print(file_hash)  # "abc123def456..."

# Hash a directory
dir_hash = hash_data("data/processed/")
print(dir_hash)  # Hashes entire directory tree

# Hash with custom options
custom_hash = hash_data(
    "data/large_dataset/",
    match=["*.csv", "*.json"],  # Only include these patterns
    ignore=["*.tmp", ".DS_Store"],  # Exclude these patterns
    jobs=8  # Use 8 parallel workers
)
```

### How Hashing Works

FlexLock uses different strategies for files and directories:

#### Files

For individual files, FlexLock:
1. Reads the file in chunks (default: 256 KB chunks)
2. Computes **xxHash128** of the contents
3. Returns a deterministic hash string
4. **Ignores** file metadata (modification time, permissions, owner)

**Why xxHash128:**
- Fast: 10-20 GB/s on modern hardware
- Collision-resistant: 128-bit hash space
- Deterministic: Same content always produces same hash

#### Directories

For directories, FlexLock:
1. Recursively scans all files in the directory tree
2. Computes hash for each file
3. Combines file hashes with tree structure
4. Uses deterministic ordering (sorted paths)
5. Returns a single hash representing the entire tree

**Directory hashing modes:**
- **Small directories (<1000 files, default)**: Hashes all individual files
- **Large directories (>1000 files)**: Falls back to directory metadata (file count + latest mtime)

**File limit:** Configurable via `FLEXLOCK_DIR_FILE_LIMIT` environment variable (default: 1000)

### Hash Caching

To avoid recomputing hashes for unchanged data, FlexLock uses a persistent cache.

**Cache location:** `~/.cache/flexlock/hashes.db` (SQLite database)

**Cache key:** `(absolute_path, file_size, modification_time)`

**How it works:**
1. When hashing a file, FlexLock checks the cache first
2. If the file hasn't changed (same size + mtime), returns cached hash
3. If changed or not in cache, computes hash and updates cache
4. Cache is thread-safe for parallel execution

**Benefits:**
- ⚡ **Instant rehashing** of unchanged files
- 🔄 **Parallel hashing** with joblib (multiple files at once)
- 🔒 **Thread-safe** database access with connection pooling
- 💾 **Persistent** across runs (survives restarts)

**Cache performance:**
```bash
# First run: hashes all files
$ time flexlock snapshot config.yml
# 10.5 seconds

# Second run: uses cache
$ time flexlock snapshot config.yml
# 0.3 seconds  ← 35x faster!
```

### Configuration

Control data hashing behavior with environment variables:

```bash
# Custom cache location
export FLEXLOCK_CACHE=/path/to/cache

# Alternative: XDG cache home
export XDG_CACHE_HOME=/path/to/cache  # Cache at $XDG_CACHE_HOME/flexlock/

# Disable caching entirely
export FLEXLOCK_NO_CACHE=1

# Increase file limit for large directories
export FLEXLOCK_DIR_FILE_LIMIT=5000

# Or set via Python
import os
os.environ["FLEXLOCK_DIR_FILE_LIMIT"] = "5000"
```

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `FLEXLOCK_CACHE` | `~/.cache` | Base cache directory |
| `XDG_CACHE_HOME` | (unset) | Alternative cache location |
| `FLEXLOCK_NO_CACHE` | `0` | Set to `1` or `true` to disable caching |
| `FLEXLOCK_DIR_FILE_LIMIT` | `1000` | Max files before fallback mode |

### Use Cases

#### 1. Data Provenance

Track which version of data was used:

```python
from flexlock import snapshot

# Track training data
snapshot(cfg, data={
    "training": "data/train.csv",
    "validation": "data/val.csv",
    "test": "data/test.csv"
})
```

The `run.lock` file will contain:
```yaml
data:
  training: abc123...
  validation: def456...
  test: ghi789...
```

#### 2. Cache Invalidation

Conditionally process data based on changes:

```python
from flexlock import hash_data

# Compute current hash
current_hash = hash_data("data/input.csv")

# Load previous hash from run.lock
with open("results/previous/run.lock") as f:
    previous = yaml.safe_load(f)
    previous_hash = previous["data"]["input"]

# Only reprocess if data changed
if current_hash != previous_hash:
    print("Data changed, reprocessing...")
    process_data()
else:
    print("Data unchanged, using cached results")
```

#### 3. Integrity Verification

Verify data hasn't been corrupted or modified:

```python
from flexlock import hash_data

# Expected hash (from documentation or previous run)
EXPECTED_HASH = "abc123def456..."

# Verify data integrity
actual_hash = hash_data("data/important_dataset.csv")

if actual_hash != EXPECTED_HASH:
    raise ValueError(f"Data corruption detected! Expected {EXPECTED_HASH}, got {actual_hash}")

print("✓ Data integrity verified")
```

#### 4. Pattern-Based Hashing

Hash only specific files in a directory:

```python
from flexlock import hash_data

# Only hash CSV files
csv_hash = hash_data("data/", match=["*.csv"])

# Hash everything except temporary files
clean_hash = hash_data("data/", ignore=["*.tmp", "*.log", ".DS_Store"])

# Combine patterns
hash_val = hash_data(
    "data/",
    match=["*.csv", "*.json"],  # Only these types
    ignore=["*_temp.csv"]        # But not temp files
)
```

### Troubleshooting

#### Large Directories

If you get warnings about exceeding the file limit:

**Option 1: Increase the limit**
```python
import os
os.environ["FLEXLOCK_DIR_FILE_LIMIT"] = "10000"

from flexlock import hash_data
hash_data("data/large_dataset/")
```

**Option 2: Hash subdirectories separately**
```python
snapshot(cfg, data={
    "subset1": "data/large_dir/subset1",
    "subset2": "data/large_dir/subset2",
    "subset3": "data/large_dir/subset3"
})
```

**Option 3: Use pattern matching**
```python
# Only hash important files
snapshot(cfg, data={
    "features": hash_data("data/large_dir/", match=["*.csv"])
})
```

#### Cache Issues

If you suspect cache corruption:

```bash
# Clear the cache
rm -rf ~/.cache/flexlock/hashes.db

# Or use a fresh cache location
export FLEXLOCK_CACHE=/tmp/flexlock_cache
python your_script.py
```

#### Slow Hashing

If hashing is slow:

1. **Check if cache is being used:**
   ```python
   # First run will be slow
   hash_data("data/large_file.csv")  # 5 seconds

   # Second run should be instant
   hash_data("data/large_file.csv")  # 0.01 seconds
   ```

2. **Increase parallel workers:**
   ```python
   # Use more CPU cores for directory hashing
   hash_data("data/", jobs=16)
   ```

3. **Consider hashing subdirectories:**
   ```python
   # Instead of hashing entire tree
   hash_data("data/")  # Slow for 100k files

   # Hash logical subsets
   hash_data("data/train/")  # Faster
   hash_data("data/test/")
   ```

#### Permission Errors

If you get permission errors accessing the cache:

```bash
# Check cache permissions
ls -la ~/.cache/flexlock/

# Fix permissions
chmod 755 ~/.cache/flexlock/
chmod 644 ~/.cache/flexlock/hashes.db

# Or use custom location
export FLEXLOCK_CACHE=/tmp/my_cache
```

### Performance Tips

1. **Leverage the cache**: First hash is slow, subsequent hashes are instant
   ```python
   # Develop with caching enabled
   hash_data("data/train.csv")  # Slow first time
   # ... make code changes ...
   hash_data("data/train.csv")  # Instant on rerun
   ```

2. **Hash directories, not individual files**: More efficient for large datasets
   ```python
   # Less efficient
   for file in glob("data/*.csv"):
       hash_data(file)

   # More efficient
   hash_data("data/", match=["*.csv"])
   ```

3. **Use parallel workers**: Default is 4, increase for better performance
   ```python
   # Utilize more cores
   hash_data("data/", jobs=os.cpu_count())
   ```

4. **Hash lazily**: Only hash when needed, not on every run
   ```python
   # Don't hash unnecessarily
   if args.track_data:
       snapshot(cfg, data={"train": "data/train.csv"})
   else:
       snapshot(cfg)  # Skip data hashing for quick iterations
   ```

5. **Disable caching for very large datasets**: If cache grows too large
   ```bash
   export FLEXLOCK_NO_CACHE=1
   python train.py
   ```

### Integration with OmegaConf Resolvers

The `${track:path}` resolver uses `hash_data()` internally:

**YAML config:**
```yaml
# Using resolver (declarative)
dataset:
  path: data/train.csv
  hash: ${track:data/train.csv}
```

**Equivalent Python:**
```python
# Using hash_data() directly (imperative)
from flexlock import hash_data
cfg.dataset.hash = hash_data("data/train.csv")
```

Both produce the same result. Use resolvers for declarative configs, or call `hash_data()` directly for dynamic logic.

**See also:** [track resolver documentation](./experimental.md#4-track---data-hash-computation)

### Summary

FlexLock's data hashing system provides:

- ✅ **Content-based hashing**: Detects any changes to data
- ✅ **Persistent caching**: Instant rehashing of unchanged data
- ✅ **Parallel execution**: Fast hashing of large directories
- ✅ **Flexible patterns**: Include/exclude files with glob patterns
- ✅ **Deterministic**: Same data always produces same hash
- ✅ **Efficient**: xxHash for speed, SQLite for caching

**Key functions:**
- `hash_data(path)`: Compute hash of file or directory
- `snapshot(..., data={...})`: Track data in snapshots
- `${track:path}`: Hash data in YAML configs

This system ensures your experiments can be precisely reproduced by verifying that input data hasn't changed.
