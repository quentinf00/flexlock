import logging
import sys

def setup_logging(log_file_path: str, level=logging.INFO):
    """
    Sets up a standardized logger that outputs to both console and a specified file.

    Args:
        log_file_path: The absolute path to the log file.
        level: The logging level (e.g., logging.INFO, logging.DEBUG).
    """
    logger = logging.getLogger("naga")
    logger.setLevel(level)
    logger.propagate = False  # Prevent messages from being passed to the root logger

    # Clear existing handlers to prevent duplicate logs if called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# Example usage (can be removed or modified later)
if __name__ == "__main__":
    logger = setup_logging("naga_test.log", level=logging.DEBUG)
    logger.info("This is an info message.")
    logger.debug("This is a debug message.")
    logger.error("This is an error message.")
