"""Decorator for loading previous stage data in Naga."""
from functools import wraps
from pathlib import Path
import yaml
from omegaconf import DictConfig, OmegaConf

from .context import run_context

def load_stage_from_path(path: str) -> dict:
    """
    Loads a stage from a given path and returns its data.
    """
    all_stages = {}
    _load_and_flatten_recursively("loaded_stage", path, all_stages)
    return all_stages

def _load_and_flatten_recursively(stage_key: str, stage_path_str: str, all_stages: dict):
    """
    Recursively loads a stage and its ancestors, adding them to the all_stages dict.
    """
    # Deduplication: If we've already processed this stage, skip.
    if stage_key in all_stages:
        return

    stage_path = Path(stage_path_str)
    lock_file = stage_path / "run.lock"

    if not lock_file.exists():
        raise FileNotFoundError(f"run.lock not found in previous stage '{stage_key}': {lock_file}")

    with open(lock_file, 'r') as f:
        stage_data = yaml.safe_load(f)

    # 1. Recurse into nested stages first (depth-first)
    if "previous_stages" in stage_data:
        for nested_key, nested_data in stage_data["previous_stages"].items():
            nested_path = nested_data.get("config", {}).get("save_dir")
            if not nested_path:
                raise ValueError(f"Could not find 'config.save_dir' in nested stage '{nested_key}' from '{stage_key}'")
            _load_and_flatten_recursively(nested_key, nested_path, all_stages)

    # 2. Add the current stage's data (without its own lineage) to the dict
    stage_data.pop("previous_stages", None)
    all_stages[stage_path.as_posix()] = stage_data


def load_stage(*stage_keys: str):
    """
    A decorator that loads the `run.lock` from one or more previous stages,
    creating a flattened, deduplicated dictionary of all ancestor runs.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapped(cfg: DictConfig, *args, **kwargs):
            if "previous_stages" not in run_context.get():
                run_context.get()["previous_stages"] = {}
            
            all_stages = run_context.get()["previous_stages"]

            for key in stage_keys:
                stage_path_str = OmegaConf.select(cfg, key)
                if stage_path_str is None:
                    raise ValueError(f"Previous stage key '{key}' not found in config.")
                
                loaded_stages = load_stage_from_path(stage_path_str)
                all_stages.update(loaded_stages)

            return fn(cfg, *args, **kwargs)
        return wrapped
    return decorator
