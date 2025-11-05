from omegaconf import OmegaConf, DictConfig
from dataclasses import is_dataclass

from typing import Any
import warnings
from dataclasses import is_dataclass, fields, MISSING
from omegaconf import OmegaConf, DictConfig


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

    if (task_to is not None) and (task_to != '.') :
        task_branch = OmegaConf.create({})
        OmegaConf.update(task_branch, task_to, task, force_add=True)
        task = task_branch
    return OmegaConf.merge(cfg, task)
