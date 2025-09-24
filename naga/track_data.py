"""Data tracking decorator for Naga."""
from functools import wraps
from omegaconf import DictConfig, OmegaConf

from .context import run_context
from .data_hash import hash_data

def track_data(*data_keys: str):
    """
    A decorator that hashes data dependencies specified in the config.

    Args:
        *data_keys: A list of dot-separated keys in the OmegaConf object
                    that point to the file or directory paths to be hashed.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapped(cfg: DictConfig, *args, **kwargs):
            # Initialize the data_hashes dictionary in the context if not present
            if "data_hashes" not in run_context.get():
                run_context.get()["data_hashes"] = {}

            # Hash each specified data path
            for key in data_keys:
                path_to_hash = OmegaConf.select(cfg, key)
                if path_to_hash is None:
                    raise ValueError(f"Data key '{key}' not found in the configuration.")
                
                # The key in the run.lock will be the same as in the config
                run_context.get()["data_hashes"][key] = hash_data(path_to_hash)

            return fn(cfg, *args, **kwargs)
        return wrapped
    return decorator
