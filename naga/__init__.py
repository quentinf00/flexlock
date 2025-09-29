"""Naga: A lightweight library for reproducible ML experiments."""

from .clicfg import clicfg
from .runlock import runlock
from .mlflow_log import mlflow_lock
from .snapshot import get_git_commit, commit_cwd
from .debug import unsafe_debug
from .resolvers import register_resolvers

# Register OmegaConf resolvers when the library is imported
register_resolvers()

__all__ = [
    "clicfg",
    "runlock",
    "mlflow_lock",
    "get_git_commit",
    "commit_cwd",
    "unsafe_debug",
]
