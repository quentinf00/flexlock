"""FlexLock: A lightweight library for reproducible ML experiments."""

from .flexcli import flexcli
from .snapshot import snapshot
from .mlflowlink import mlflowlink
from .snapshot import get_git_commit, commit_cwd
from .debug import debug_on_fail
from .resolvers import register_resolvers
from .logging import setup_flexlock_logging

# Register OmegaConf resolvers when the library is imported
register_resolvers()
# Setup logging
setup_flexlock_logging()

__all__ = [
    "flexcli",
    "snapshot",
    "mlflowlink",
    "get_git_commit",
    "commit_cwd",
    "debug_on_fail",
]
