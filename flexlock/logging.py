import logging
import sys
import os
from pathlib import Path

_FLEXLOCK_LOGGING_CONFIGURED = False
_DEFAULT_FORMAT = "%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s"

def setup_flexlock_logging():
    """
    Configures the root logger for FlexLock applications.
    This function is called automatically when the flexlock package is imported.
    It sets up a default console logger.
    """
    global _FLEXLOCK_LOGGING_CONFIGURED
    if _FLEXLOCK_LOGGING_CONFIGURED:
        return

    root_logger = logging.getLogger()
    
    # If the root logger already has handlers, we assume the user has configured it.
    if root_logger.hasHandlers():
        _FLEXLOCK_LOGGING_CONFIGURED = True
        return

    # Set level based on environment variable
    level = logging.DEBUG if os.environ.get("FLEXLOCK_DEBUG") == "1" else logging.INFO
    root_logger.setLevel(level)

    # Default console handler
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(_DEFAULT_FORMAT)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    _FLEXLOCK_LOGGING_CONFIGURED = True

def add_file_handler(logfile: Path, level: int, quiet: bool):
    """
    Adds a file handler to the root logger and optionally removes console handlers.
    """
    root_logger = logging.getLogger()
    
    # Set the overall logger level if the new level is lower
    if level < root_logger.level:
        root_logger.setLevel(level)

    # Add the file handler
    formatter = logging.Formatter(_DEFAULT_FORMAT)
    file_handler = logging.FileHandler(logfile)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    # If quiet is True, remove console handlers
    if quiet:
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                if handler.stream in (sys.stdout, sys.stderr):
                    root_logger.removeHandler(handler)
