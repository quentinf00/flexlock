"""CLI entry point for FlexLock."""

import sys
import functools
from .runner import FlexLockRunner


def flexcli(fn):
    """
    Decorator that allows a function to be:
    1. Imported and used programmatically (logic preserved).
    2. Run as a CLI entry point (FlexLockRunner invoked).
    """
    @functools.wraps(fn)
    def wrapper(cfg=None, **kwargs):
        # Mode 1: Programmatic
        if cfg is not None or kwargs:
            return fn(cfg, **kwargs)

        # Mode 2: CLI
        # We assume if no args passed, we are in CLI mode
        runner = FlexLockRunner()
        # In a real impl, you might want to map 'fn' to a default config logic here
        return runner.run()

    # Store original for py2cfg inspection
    wrapper._original_fn = fn
    return wrapper


def main():
    """Entry point for the 'flexlock' command."""
    FlexLockRunner().run()