"""Configuration decorator for FlexLock with progressive framework support."""

import sys
import os
import functools
from loguru import logger
import inspect
from typing import Dict, Optional
from .runner import FlexLockRunner
from .utils import py2cfg, instantiate
from .debug import debug_on_fail
from .snapshot import snapshot


def _is_jupyter_or_interactive():
    """
    Check if running in Jupyter/IPython interactive environment.

    Returns True for:
    - Jupyter notebooks
    - Jupyter console
    - VSCode interactive windows
    - IPython REPL
    """
    try:
        from IPython import get_ipython
        ipython = get_ipython()
        if ipython is not None:
            return True
    except ImportError:
        pass

    # Also check for python -i
    if hasattr(sys, 'ps1'):
        return True

    return False


def _should_use_cli_mode():
    """
    Determine if we should parse CLI arguments or execute directly.

    Returns False if:
    - sys.argv[0] is ipykernel_launcher.py (Jupyter kernel startup)
    - sys.argv has kernel arguments like --f=... or -f ...

    Returns True if:
    - Normal CLI execution
    - IPython %run command (sys.argv[0] is the script name)
    - Script execution

    This allows:
    - %run file.py -o param=2 → Parse CLI args ✓
    - train() in Jupyter → Don't parse ✗
    - ipykernel_launcher.py --f=kernel.json → Don't parse ✗
    """
    if len(sys.argv) == 0:
        # No arguments, likely interactive
        logger.debug("No sys.argv detected, assuming interactive mode")
        return False

    # Check sys.argv[0] for kernel launcher
    if sys.argv[0].endswith('ipykernel_launcher.py'):
        logger.debug(f"Detected ipykernel_launcher in sys.argv[0], skipping CLI parsing")
        return False

    # Check for kernel connection file arguments
    for arg in sys.argv[1:]:
        if '--f=' in arg or arg.startswith('-f'):
            # Check if next arg or same arg contains .json (connection file)
            if '.json' in arg or (sys.argv.index(arg) + 1 < len(sys.argv) and '.json' in sys.argv[sys.argv.index(arg) + 1]):
                logger.debug(f"Detected Jupyter kernel connection file argument: {arg}")
                return False

    # If we get here, either:
    # - Normal script execution
    # - %run command (sys.argv[0] is script name, args look normal)
    # Both should parse CLI
    logger.debug(f"CLI mode enabled. sys.argv: {sys.argv}")
    return True


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
                # Direct call with arguments - execute immediately
                # Apply debug wrapper if enabled
                if os.environ.get("FLEXLOCK_DEBUG", "false").lower() in ("1", "true"):
                    return debug_on_fail(fn)(*args, **kwargs)
                else:
                    return fn(*args, **kwargs)

            # Called with no arguments - check if we should parse CLI
            # 1. Build Base Config from signature + defaults
            base_cfg = py2cfg(fn, **defaults)

            # 2. Inject Snapshot Config if provided
            if snapshot_config:
                base_cfg["_snapshot_"] = snapshot_config

            # 3. Determine execution mode
            if _should_use_cli_mode():
                # CLI mode (normal script or %run): Launch Runner to parse arguments
                runner = FlexLockRunner()
                return runner.run(base_cfg=base_cfg)
            else:
                # Interactive mode (Jupyter kernel): Execute directly with defaults
                # This happens when train() is called in Jupyter without %run
                logger.info("Interactive mode detected: Executing with defaults (no CLI parsing)")

                # Execute with debug wrapper if enabled
                if os.environ.get("FLEXLOCK_DEBUG", "false").lower() in ("1", "true"):
                    return debug_on_fail(fn)(**defaults)
                else:
                    return fn(**defaults)

        wrapper._original_fn = fn
        wrapper._defaults = defaults  # Store metadata
        return wrapper

    # Support both @flexcli and @flexcli(...) syntax
    if _func is None:
        return decorator
    else:
        return decorator(_func)
