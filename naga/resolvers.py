from dataclasses import replace
from omegaconf import OmegaConf
from .data_hash import hash_data
from .load_stage import load_stage_from_path
from .context import run_context

def track_resolver(path: str) -> str:
    """
    OmegaConf resolver to track a data path.
    It computes the hash of the data and stores it in the run context.
    """
    data_hash_value = hash_data(path)
    run_context.get().setdefault('data_hashes', {})[path] = data_hash_value
    return path

def stage_resolver(path: str) -> str:
    """
    OmegaConf resolver to load a previous stage.
    It loads the run.lock from the given path and stores it in the run context.
    """
    stage_info = load_stage_from_path(path)
    run_context.get().setdefault('previous_stages', {})[path] = stage_info
    return path

def register_resolvers():
    """
    Registers the naga resolvers with OmegaConf.
    """
    OmegaConf.register_new_resolver("track", track_resolver, replace=True)
    OmegaConf.register_new_resolver("stage", stage_resolver, replace=True)
