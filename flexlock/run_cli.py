"""CLI entry point for FlexLock runner."""

import os
import sys
from loguru import logger
from flexlock.runner import FlexLockRunner


def main():
    """
    CLI entry point for flexlock-run command.

    This is a standalone CLI that provides direct access to FlexLockRunner
    without requiring a Python script with @flexcli decorator.

    Usage:
        flexlock-run --config experiment.yml
        flexlock-run --defaults module.config:defaults --config exp.yml
        flexlock-run --config exp.yml --select experiments.exp1
        flexlock-run --sweep-file sweep.yaml --n_jobs 4
    """
    # Make the current working directory importable so users can pass
    # `-d mypkg.module.var` for a package in their project without having
    # to set PYTHONPATH manually. Mirrors what `python -m mypkg` would do.
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        runner = FlexLockRunner()
        runner.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"FlexLock run failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
