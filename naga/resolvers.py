from omegaconf import OmegaConf
from .data_hash import hash_data
from .load_stage import load_stage_from_path

def track_resolver(path: str) -> str:
    """
    OmegaConf resolver that computes and returns the hash of a data path.
    """
    return hash_data(path)

def stage_resolver(path: str) -> dict:
    """
    OmegaConf resolver that loads a previous stage's run.lock and returns its content.
    """
    return load_stage_from_path(path)

def register_resolvers():
    """
    Registers the naga resolvers with OmegaConf.
    """
    OmegaConf.register_new_resolver("track", track_resolver)
    OmegaConf.register_new_resolver("stage", stage_resolver)
