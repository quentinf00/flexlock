"""FlexLock: A lightweight library for reproducible ML experiments."""

__version__ = "0.4.1"

from loguru import logger

logger.disable("flexlock")

from .flexcli import flexcli
from .snapshot import snapshot
from .mlflow import mlflow_context
from .debug import debug_on_fail
from .resolvers import register_resolvers
from .api import Project


def submit(config=None, **kwargs):
    """Submit a configuration without instantiating a :class:`Project`.

    Sugar over ``Project().submit(config, **kwargs)`` — use when you have a
    ready ``DictConfig`` and don't need the multi-stage pipeline plumbing
    (``proj.get``, ``proj.defaults``, etc.). All ``Project.submit`` kwargs
    (``sweep``, ``slurm_config``, ``smart_run``, ``overrides``, …) are
    forwarded as-is.

    Example::

        from flexlock import submit, py2cfg
        cfg = py2cfg(train, lr=0.01, save_dir='outputs/train')
        result = submit(cfg, slurm_config='configs/slurm_gpu.yaml')
    """
    return Project().submit(config, **kwargs)
from .utils import (
    py2cfg,
    load_python_defaults,
    extract_tracking_info,
    load_sweep,
    enqueue_to_file,
    log_to_file,
    parse_sweep_string,
    select_and_freeze_root_refs,
)
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
    "submit",
    "py2cfg",
    "load_python_defaults",
    "load_sweep",
    "enqueue_to_file",
    "log_to_file",
    "parse_sweep_string",
    "select_and_freeze_root_refs",
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
