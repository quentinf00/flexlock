"""Utility functions for FlexLock."""

from omegaconf import OmegaConf, DictConfig, ListConfig
from dataclasses import is_dataclass
from contextlib import contextmanager
from loguru import logger
import importlib
import functools


from typing import Any
import warnings
from dataclasses import fields


def to_dictconfig(incfg):
    """
    Convert various config formats (dataclass, dict, class instance, DictConfig)
    into a DictConfig object.
    Warns if dataclass fields are missing type annotations.
    """

    # Case 1: already DictConfig
    if isinstance(incfg, DictConfig):
        return incfg

    # Case 2: dataclass
    if is_dataclass(incfg):
        # Find missing type hints
        missing_types = [f.name for f in fields(incfg) if f.type is None]
        if missing_types:
            warnings.warn(
                f"Dataclass {type(incfg).__name__} has fields without type hints: "
                f"{', '.join(missing_types)}. "
                "These fields will be ignored by OmegaConf.structured().",
                UserWarning,
                stacklevel=2,
            )
        return OmegaConf.structured(incfg)

    # Case 3: dict
    if isinstance(incfg, dict):
        return OmegaConf.create(incfg)

    # Case 4: plain class instance
    if hasattr(incfg, "__dict__"):
        obj_dict = {
            k: v
            for k, v in vars(incfg).items()
            if not k.startswith("_") and not callable(v)
        }
        return OmegaConf.create(obj_dict)

    # Case 5: __slots__-based classes
    if hasattr(incfg, "__slots__"):
        obj_dict = {slot: getattr(incfg, slot) for slot in incfg.__slots__}
        return OmegaConf.create(obj_dict)

    # Fallback: try creating directly
    return OmegaConf.create(incfg)


def merge_task_into_cfg(cfg: DictConfig, task: Any, task_to: str | None) -> DictConfig:
    """Merge a task into the config."""
    # Create a minimal config with just the task structure

    if (task_to is not None) and (task_to != "."):
        task_branch = OmegaConf.create({})
        OmegaConf.update(task_branch, task_to, task, force_add=True)
        task = task_branch
    return OmegaConf.merge(cfg, task)


@contextmanager
def log_to_file(path):
    # Add sink
    lid = logger.add(path)
    try:
        yield
    finally:
        # Remove sink
        logger.remove(lid)


def instantiate(config, *args, **kwargs):
    """
    Recursively instantiate objects defined in dictionaries with a "_target_" key.

    Args:
        config: The configuration dictionary (or value).
        *args, **kwargs: Additional arguments to pass to the root object.
    """
    # 1. Base case: If config is not a dict or list, return it as is.
    if not isinstance(config, (dict, list, DictConfig, ListConfig)):
        return config

    if isinstance(config, (list, ListConfig)):
        return [instantiate(item) for item in config]

    # config is a dict
    # 2. Check if this dict represents a target object
    if "_target_" not in config:
        # It's just a regular dictionary, but we should check values recursively
        return {k: instantiate(v) for k, v in config.items()}

    # 3. Prepare the configuration
    # Copy to avoid mutating the original dict
    conf_copy = config.copy()
    target_path = conf_copy.pop("_target_")
    is_partial = conf_copy.pop("_partial_", False)

    # 4. recursive instantiation of arguments
    # We instantiate the arguments BEFORE creating the main object
    init_args = {k: instantiate(v) for k, v in conf_copy.items()}

    # Merge with runtime args (kwargs override config)
    init_args.update(kwargs)

    # 5. Import the class or function
    try:
        module_path, class_name = target_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        target_class = getattr(module, class_name)
    except (ValueError, ImportError, AttributeError) as e:
        raise ImportError(f"Could not import target '{target_path}': {e}")

    # 6. Instantiate or return partial
    if is_partial:
        return functools.partial(target_class, *args, **init_args)

    return target_class(*args, **init_args)
