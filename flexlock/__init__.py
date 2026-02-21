"""FlexLock: A lightweight library for reproducible ML experiments."""

__version__ = "0.3.2"

from loguru import logger

logger.disable("flexlock")

from .flexcli import flexcli
from .snapshot import snapshot
from .mlflow import mlflow_context
from .debug import debug_on_fail
from .resolvers import register_resolvers
from .api import Project
from .utils import py2cfg, load_python_defaults, extract_tracking_info
from .runner import FlexLockRunner
from .data_hash import hash_data
from .git_utils import get_git_tree_hash

# Import exceptions for public API
from .exceptions import (
    FlexLockError,
    FlexLockConfigError,
    FlexLockExecutionError,
    FlexLockSnapshotError,
    FlexLockValidationError,
    FlexLockCacheError,
    FlexLockBackendError,
)

# Register OmegaConf resolvers when the library is imported
register_resolvers()

__all__ = [
    "__version__",
    "flexcli",
    "snapshot",
    "mlflow_context",
    "debug_on_fail",
    "Project",
    "py2cfg",
    "load_python_defaults",
    "FlexLockRunner",
    "hash_data",
    "get_git_tree_hash",
    # Exceptions
    "FlexLockError",
    "FlexLockConfigError",
    "FlexLockExecutionError",
    "FlexLockSnapshotError",
    "FlexLockValidationError",
    "FlexLockCacheError",
    "FlexLockBackendError",
]
