"""Custom exceptions for FlexLock."""


class FlexLockError(Exception):
    """Base exception for all FlexLock errors."""

    pass


class FlexLockConfigError(FlexLockError):
    """Raised when there is an error in configuration."""

    pass


class FlexLockExecutionError(FlexLockError):
    """Raised when there is an error during execution."""

    pass


class FlexLockSnapshotError(FlexLockError):
    """Raised when there is an error creating or loading snapshots."""

    pass


class FlexLockValidationError(FlexLockError):
    """Raised when validation of inputs fails."""

    pass


class FlexLockCacheError(FlexLockError):
    """Raised when there is an error with smart run caching."""

    pass


class FlexLockBackendError(FlexLockError):
    """Raised when there is an error with HPC backends (Slurm/PBS)."""

    pass


class UnresolvedInterpolationError(FlexLockConfigError):
    """Raised when a sub-node interpolation references a key that is not present
    in the sub-tree and cannot be resolved against the root config either."""

    pass
