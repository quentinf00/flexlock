# Reference

## Environment Variables

All FlexLock environment variables are prefixed with `FLEXLOCK_`.

### Parallel Execution

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLEXLOCK_POLL_INTERVAL` | int | `10` | Poll interval in seconds for checking task status |
| `FLEXLOCK_LOG_FREQUENCY` | int | `15` | Log frequency in seconds for progress updates |
| `FLEXLOCK_DEFAULT_N_JOBS` | int | `1` | Default number of parallel jobs |
| `FLEXLOCK_DEFAULT_TIMEOUT` | int | `3600` | Default timeout in seconds for HPC jobs |

### Smart Run / Caching

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLEXLOCK_WARN_SMART_RUN` | bool | `true` | Warn when `smart_run=True` but `search_dirs=None` |

### Data Hashing

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLEXLOCK_CACHE` | path | `~/.cache` | Base directory for FlexLock cache |
| `FLEXLOCK_NO_CACHE` | bool | `false` | Disable hash caching |
| `FLEXLOCK_DIR_FILE_LIMIT` | int | `1000` | Max files to hash in a directory before warning |
| `FLEXLOCK_CACHE_DIR_FILE_LIMIT` | int | `1000` | Override file limit for cache operations |

### Timestamp Format

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLEXLOCK_TIMESTAMP_FORMAT` | str | `%Y-%m-%dT%H-%M-%S` | Format for directory timestamps |

### Logging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLEXLOCK_CONFIGURE_LOGGING` | bool | `true` | Whether to configure logging by default |

### Debug Mode

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLEXLOCK_DEBUG` | bool | `false` | Enable debug mode (drops into debugger on error) |
| `FLEXLOCK_NODEBUG` | bool | `false` | Disable debug mode (takes precedence over `FLEXLOCK_DEBUG`) |
| `FLEXLOCK_DEBUG_STRATEGY` | str | `auto` | Debug strategy: `auto`, `pdb`, or `inject` |

**Debug strategies:**
- `auto`: Detect environment - use PDB for scripts, inject locals for notebooks/interactive
- `pdb`: Always use PDB post-mortem debugger
- `inject`: Always inject locals into caller's namespace (for notebooks)

### Display

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLEXLOCK_MAX_DISPLAY_ITEMS` | int | `10` | Maximum items to show in summaries |

### Validation

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLEXLOCK_STRICT_VALIDATION` | bool | `true` | Enable strict configuration validation |

### Boolean Values

Boolean environment variables accept:
- **True**: `1`, `true`, `yes`, `on`
- **False**: `0`, `false`, `no`, `off`

## Exceptions

FlexLock defines a hierarchy of exceptions for error handling.

### Exception Hierarchy

```
FlexLockError (base)
├── FlexLockConfigError
├── FlexLockExecutionError
├── FlexLockSnapshotError
├── FlexLockValidationError
├── FlexLockCacheError
└── FlexLockBackendError
```

### Exception Reference

#### `FlexLockError`

Base exception for all FlexLock errors. Catch this to handle any FlexLock-specific error.

```python
from flexlock import FlexLockError

try:
    result = proj.submit(cfg)
except FlexLockError as e:
    print(f"FlexLock error: {e}")
```

#### `FlexLockConfigError`

Raised when there is an error in configuration.

**Common causes:**
- Invalid configuration structure
- Missing required keys
- Invalid `_target_` specification
- OmegaConf interpolation errors

```python
from flexlock import FlexLockConfigError

try:
    cfg = proj.get('nonexistent_key')
except FlexLockConfigError as e:
    print(f"Configuration error: {e}")
```

#### `FlexLockExecutionError`

Raised when there is an error during execution.

**Common causes:**
- Target function raises an exception
- Import errors for `_target_`
- Argument mismatches

```python
from flexlock import FlexLockExecutionError

try:
    result = proj.submit(cfg)
except FlexLockExecutionError as e:
    print(f"Execution failed: {e}")
```

#### `FlexLockSnapshotError`

Raised when there is an error creating or loading snapshots.

**Common causes:**
- Cannot write to `save_dir`
- Corrupted `run.lock` file
- Git repository errors during snapshot
- Invalid data paths for hashing

```python
from flexlock import FlexLockSnapshotError

try:
    snapshot(cfg, repos={'main': '.'})
except FlexLockSnapshotError as e:
    print(f"Snapshot error: {e}")
```

#### `FlexLockValidationError`

Raised when validation of inputs fails.

**Common causes:**
- Invalid parameter types
- Out-of-range values
- Missing required parameters

```python
from flexlock import FlexLockValidationError

try:
    proj.submit(cfg, n_jobs=-1)  # Invalid
except FlexLockValidationError as e:
    print(f"Validation error: {e}")
```

#### `FlexLockCacheError`

Raised when there is an error with smart run caching.

**Common causes:**
- Cannot read cached `run.lock`
- Fingerprint comparison errors
- Corrupted cache database

```python
from flexlock import FlexLockCacheError

try:
    result = proj.get_result(cfg, search_dirs=['outputs/'])
except FlexLockCacheError as e:
    print(f"Cache error: {e}")
```

#### `FlexLockBackendError`

Raised when there is an error with HPC backends (Slurm/PBS).

**Common causes:**
- Invalid backend configuration
- Job submission failure
- Queue/scheduler errors
- Task database lock issues

```python
from flexlock import FlexLockBackendError

try:
    result = proj.submit(cfg, pbs_config='pbs.yaml')
except FlexLockBackendError as e:
    print(f"HPC backend error: {e}")
```

### Catching Multiple Exceptions

```python
from flexlock import (
    FlexLockError,
    FlexLockConfigError,
    FlexLockExecutionError,
)

try:
    cfg = proj.get('train')
    result = proj.submit(cfg)
except FlexLockConfigError as e:
    print(f"Fix your configuration: {e}")
except FlexLockExecutionError as e:
    print(f"Execution failed: {e}")
except FlexLockError as e:
    print(f"Other FlexLock error: {e}")
```
