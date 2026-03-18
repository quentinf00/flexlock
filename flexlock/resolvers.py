"""OmegaConf resolvers for FlexLock."""

from omegaconf import OmegaConf, DictConfig
from .data_hash import hash_data
from .load_stage import load_stage_from_path
from datetime import datetime
import re
from pathlib import Path
from functools import wraps
from . import config


def now_resolver(fmt: str = None) -> str:
    """
    OmegaConf resolver that returns the current time as a formatted string.

    Args:
        fmt: Format string for strftime (defaults to config.TIMESTAMP_FORMAT)
    """
    if fmt is None:
        fmt = config.TIMESTAMP_FORMAT
    return datetime.now().strftime(fmt)


def latest_resolver(path_glob: str) -> str:
    """
    OmegaConf resolver that returns the latest path matching the given pattern
    """
    from glob import glob
    import os
    from pathlib import Path
    from loguru import logger

    # Expand user (~) and resolve the path
    path_glob = os.path.expanduser(path_glob)

    # Find all paths matching the pattern
    matching_paths = glob(path_glob, recursive=True)

    if not matching_paths:
        # If no matches are found, warn and return the original pattern
        logger.warning(f"No paths found matching pattern: {path_glob}")
        return path_glob

    # Find the latest path by modification time
    latest_path = max(matching_paths, key=os.path.getmtime)

    return latest_path


def vinc_resolver(path: str, fmt: str = "_{i:04d}") -> str:
    """
    OmegaConf resolver that finds the highest existing version of a folder/file
    and returns the next versioned path as a string. Results are cached to ensure
    consistent values within a single execution.
    """
    # Compute the result (original logic)
    p = Path(path)
    parent_dir = p.parent
    base_name = p.name

    regex_pattern = re.sub(r"\{i.*\}", r"(\\d+)", fmt)
    regex = re.compile(f"^{re.escape(base_name)}{regex_pattern}")

    highest_version = -1
    if not parent_dir.exists():
        parent_dir.mkdir(parents=True, exist_ok=True)
    for item in parent_dir.glob(f"{base_name}*"):
        match = regex.match(item.name)
        if match:
            version = int(match.group(1))
            if version > highest_version:
                highest_version = version

    next_version = highest_version + 1
    version_str = fmt.format(i=next_version)

    return str(parent_dir / f"{base_name}{version_str}")


def run_lock_resolver(run_dir: str, key: str, default: str = None) -> str:
    """
    OmegaConf resolver that reads a field from an upstream run.lock.

    Navigates a dot-separated key path into the run.lock YAML.
    Returns the value as a string, or the default if the key is not found.

    Usage in configs:
        ${run_lock:path/to/run_dir,config.datamodule.stats_file}
        ${run_lock:${run_dir},config.lit_module.regression_checkpoint_path,null}
    """
    from loguru import logger
    import yaml

    lock_path = Path(run_dir) / "run.lock"
    if not lock_path.exists():
        if default is not None:
            logger.warning(f"run_lock resolver: no run.lock at {run_dir}, using default")
            return default
        raise FileNotFoundError(f"run_lock resolver: no run.lock found in {run_dir}")

    with open(lock_path) as f:
        data = yaml.safe_load(f)

    # Navigate dot-path
    value = data
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            if default is not None:
                return default
            raise KeyError(
                f"run_lock resolver: key '{key}' not found in {lock_path} "
                f"(failed at '{part}')"
            )

    # Convert to string for OmegaConf
    if value is None:
        return default if default is not None else ""
    return str(value)


def register_resolvers():
    """
    Registers the flexlock resolvers with OmegaConf.
    """
    OmegaConf.register_new_resolver("now", now_resolver)
    OmegaConf.register_new_resolver("vinc", vinc_resolver)
    OmegaConf.register_new_resolver("latest", latest_resolver)
    OmegaConf.register_new_resolver("run_lock", run_lock_resolver, use_cache=False)
