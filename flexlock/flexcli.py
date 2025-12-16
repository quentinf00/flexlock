"""Configuration decorator for FlexLock with progressive framework support."""

import sys
import functools
from loguru import logger
import inspect
from typing import Dict, Optional
from .runner import FlexLockRunner
from .utils import py2cfg


def flexcli(_func=None, snapshot_config: Optional[Dict] = None, **defaults):
    """
    Decorator for FlexLock entry points with progressive framework support.

    Args:
        snapshot_config: Dict defining repos, data, and lineage tracking.
                         Injects '_snapshot_' into the config.
        **defaults: Default values for the function arguments.

    Usage:
        @flexcli
        def main(param=10, db="postgres"): ...

        @flexcli(param=10)
        def main(param, db="postgres"): ...

        @flexcli(
            data_path="./data/mnist",
            snapshot_config={
                "repos": {"main": "."},
                "data": {"input_dataset": "${data_path}"}
            }
        )
        def train(data_path, save_dir=None): ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if len(args) > 0 or len(kwargs) > 0:
                return fn(*args, **kwargs)

            # 1. Build Base Config from signature + defaults
            base_cfg = py2cfg(fn, **defaults)
            
            # 2. Inject Snapshot Config if provided
            if snapshot_config:
                base_cfg["_snapshot_"] = snapshot_config

            # 3. Launch Runner with this base
            runner = FlexLockRunner()
            return runner.run(base_cfg=base_cfg)

        wrapper._original_fn = fn
        wrapper._defaults = defaults  # Store metadata
        return wrapper

    # Support both @flexcli and @flexcli(...) syntax
    if _func is None:
        return decorator
    else:
        return decorator(_func)
