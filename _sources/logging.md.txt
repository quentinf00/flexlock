# Logging Configuration in FlexLock

FlexLock uses [Loguru](https://loguru.readthedocs.io/) as its logging backend, providing a simple and powerful logging experience. This guide explains how to configure logging to take full advantage of FlexLock's features, including log persistence and automatic MLflow logging.

## Logging Best Practices

### Basic Loguru Integration

FlexLock works seamlessly with Loguru's `logger` object. You can use it directly in your code:

```python
from loguru import logger
from flexlock import flexcli

class Config:
    param: int = 1
    save_dir: str = "results/experiment"

@flexcli(config_class=Config)
def main(cfg: Config):
    logger.info(f"Starting experiment with param: {cfg.param}")
    logger.debug(f"Processing in directory: {cfg.save_dir}")
    
    # Your experiment logic here
    result = cfg.param * 2
    
    logger.success(f"Experiment completed successfully: {result}")

if __name__ == '__main__':
    main()
```

## Automatic Log Persistence

To ensure your logs are persistent and available for later analysis, we recommend adding a file sink to your `save_dir` at the beginning of your function:

```python
from loguru import logger
from flexlock import flexcli
from pathlib import Path

class Config:
    param: int = 1
    save_dir: str = "results/experiment"

@flexcli(config_class=Config)
def main(cfg: Config):
    # Add file logging to save_dir for persistence
    log_file = Path(cfg.save_dir) / "experiment.log"
    logger.add(log_file, rotation="10 MB", retention="10 days")
    
    logger.info(f"Starting experiment with param: {cfg.param}")
    
    # Your experiment logic here
    result = cfg.param * 2
    
    logger.success(f"Experiment completed successfully: {result}")

if __name__ == '__main__':
    main()
```

This approach:
- Stores logs in your experiment's `save_dir` for easy access
- Enables automatic log rotation to manage disk space
- Provides long-term retention for historical analysis
- Integrates with FlexLock's snapshot system for complete experiment provenance

## Automatic MLflow Logging

When you use a file sink as shown above with the filename `experiment.log`, FlexLock automatically logs this file to MLflow when you use the `mlflowlink` context manager:

```python
from loguru import logger
from flexlock import flexcli, snapshot
from flexlock.mlflowlink import mlflowlink
from pathlib import Path

class Config:
    param: int = 1
    save_dir: str = "results/experiment"

@flexcli(config_class=Config)
def main(cfg: Config):
    # Add file logging for persistence and MLflow integration
    log_file = Path(cfg.save_dir) / "experiment.log"
    logger.add(log_file)
    
    logger.info(f"Starting experiment with param: {cfg.param}")
    
    # Your experiment logic
    result = cfg.param * 2
    
    # Create snapshot
    snapshot(config=cfg, save_dir=cfg.save_dir)
    
    # Log to MLflow with automatic artifact logging
    with mlflowlink(cfg.save_dir) as run:
        logger.info(f"Logged to MLflow run: {run.info.run_id}")
        logger.success(f"Experiment completed successfully: {result}")

if __name__ == '__main__':
    main()
```

With this setup, the `experiment.log` file will be automatically logged as an artifact to MLflow, making your logs accessible through the MLflow UI.

## Enabling FlexLock's Internal Logging

To see internal FlexLock logging messages, you can configure the log level for the `flexlock` module:

```python
import logging
from loguru import logger
from flexlock import flexcli

class Config:
    param: int = 1
    save_dir: str = "results/experiment"

@flexcli(config_class=Config)
def main(cfg: Config):
    # Enable FlexLock internal logging
    logging.getLogger('flexlock').setLevel(logging.DEBUG)
    
    # Add a handler to capture flexlock logs with loguru
    logger.add("flexlock_internal.log", level="DEBUG", filter=lambda record: "flexlock" in record["name"])
    
    logger.info(f"Starting experiment with param: {cfg.param}")
    
    # Your experiment logic here
    
    logger.success("Experiment completed")

if __name__ == '__main__':
    main()
```

## CLI Logging Options

FlexLock's `@flexcli` decorator also provides built-in logging options:

```bash
# Basic run with console logging and file logging to save_dir/experiment.log
python experiment.py

# Enable debug logging
python experiment.py --verbose
# Or set environment variable: FLEXLOCK_DEBUG=1 python experiment.py

# Control log level via environment variable
LOGURU_LEVEL=DEBUG python experiment.py
```

## Advanced Loguru Configuration

For more sophisticated logging setups, you can use Loguru's full feature set:

```python
from loguru import logger
from flexlock import flexcli
from pathlib import Path

class Config:
    param: int = 1
    save_dir: str = "results/experiment"

@flexcli(config_class=Config)
def main(cfg: Config):
    # Configure multiple log handlers
    log_file = Path(cfg.save_dir) / "experiment.log"
    
    # Add file logging with rotation and filtering
    logger.add(
        log_file,
        rotation="500 MB",      # Rotate when file reaches 500MB
        retention="10 days",    # Keep logs for 10 days
        level="INFO",           # Log INFO and above
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {function}:{line} | {message}"
    )
    
    # Add console logging with different format
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
        level="INFO"
    )
    
    logger.info(f"Starting experiment with param: {cfg.param}")
    
    # Your experiment logic here
    result = cfg.param * 2
    
    logger.success(f"Experiment completed successfully: {result}")

if __name__ == '__main__':
    main()
```

## Logging in Parallel Execution

When running experiments in parallel, each worker will write to the same log file. To distinguish between different workers, you can include process information in your log format:

```python
from loguru import logger
from flexlock import flexcli
from pathlib import Path
import os

class Config:
    param: int = 1
    save_dir: str = "results/experiment"

@flexcli(config_class=Config)
def main(cfg: Config):
    log_file = Path(cfg.save_dir) / "experiment.log"
    
    # Include process ID in logs for parallel execution
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | PID:{process} | {level} | {function}:{line} | {message}",
        enqueue=True  # Thread-safe logging for parallel execution
    )
    
    logger.info(f"Process {os.getpid()} starting experiment with param: {cfg.param}")
    
    # Your experiment logic here
    
    logger.success(f"Process {os.getpid()} completed successfully")

if __name__ == '__main__':
    main()
```

## Key Recommendations

1. **Always add a file sink**: Use `logger.add(cfg.save_dir / "experiment.log")` to ensure log persistence
2. **Use loguru**: It's the logging framework FlexLock is built around
3. **Enable flexlock logging**: Use `logging.getLogger('flexlock').setLevel()` to see internal messages
4. **Enable parallel-safe logging**: Use `enqueue=True` when running in parallel
5. **Include context**: Use structured logging with relevant configuration values