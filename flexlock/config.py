"""Configuration and constants for FlexLock.

This module defines default values and environment variable overrides.
All environment variables are prefixed with FLEXLOCK_.
"""

import os


def get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable."""
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_float(key: str, default: float) -> float:
    """Get float from environment variable."""
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_env_bool(key: str, default: bool) -> bool:
    """Get boolean from environment variable."""
    value = os.environ.get(key, '').lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    elif value in ('0', 'false', 'no', 'off'):
        return False
    return default


# ==================== Parallel Execution ====================

# Poll interval for checking task status (seconds)
POLL_INTERVAL = get_env_int('FLEXLOCK_POLL_INTERVAL', 10)

# Log frequency for progress updates (seconds)
LOG_FREQUENCY = get_env_int('FLEXLOCK_LOG_FREQUENCY', 15)

# Default number of parallel jobs
DEFAULT_N_JOBS = get_env_int('FLEXLOCK_DEFAULT_N_JOBS', 1)

# Default timeout for waiting on HPC jobs (seconds, None = no timeout)
_timeout_str = os.environ.get('FLEXLOCK_DEFAULT_TIMEOUT')
DEFAULT_TIMEOUT = int(_timeout_str) if _timeout_str else 3600


# ==================== Smart Run / Caching ====================

# Whether to warn when smart_run=True but search_dirs=None
WARN_SMART_RUN_NO_SEARCH_DIRS = get_env_bool('FLEXLOCK_WARN_SMART_RUN', True)


# ==================== Timestamp Format ====================

# Standard timestamp format for directory names
# ISO 8601 compatible: YYYY-MM-DDTHH-MM-SS
TIMESTAMP_FORMAT = os.environ.get('FLEXLOCK_TIMESTAMP_FORMAT', '%Y-%m-%dT%H-%M-%S')

# Timestamp format for snapshots (ISO 8601 with microseconds)
SNAPSHOT_TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'


# ==================== Database ====================

# Database filename suffix
DB_FILENAME_SUFFIX = '.tasks.db'

# Default database filename pattern
DB_FILENAME_PATTERN = 'run.lock{suffix}'


# ==================== Logging ====================

# Whether to configure logging by default
CONFIGURE_LOGGING = get_env_bool('FLEXLOCK_CONFIGURE_LOGGING', True)


# ==================== Debug Mode ====================

# Debug mode enabled
DEBUG = get_env_bool('FLEXLOCK_DEBUG', False)

# Debug mode disabled (takes precedence)
NODEBUG = get_env_bool('FLEXLOCK_NODEBUG', False)

# Debug strategy: 'auto', 'pdb', or 'inject'
DEBUG_STRATEGY = os.environ.get('FLEXLOCK_DEBUG_STRATEGY', 'auto')


# ==================== Display ====================

# Maximum number of items to show in summaries
MAX_DISPLAY_ITEMS = get_env_int('FLEXLOCK_MAX_DISPLAY_ITEMS', 10)


# ==================== Validation ====================

# Whether to validate configuration strictly
STRICT_VALIDATION = get_env_bool('FLEXLOCK_STRICT_VALIDATION', True)
