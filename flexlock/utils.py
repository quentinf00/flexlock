from omegaconf import OmegaConf, DictConfig
from dataclasses import is_dataclass

def to_dictconfig(incfg):
    if is_dataclass(incfg):
        cfg = OmegaConf.structured(incfg)
    elif isinstance(incfg, dict):
        cfg = OmegaConf.create(incfg)
    elif isinstance(incfg, DictConfig): 
        cfg = incfg
    else: 
        # For any other type, try to create an OmegaConf from it
        cfg = OmegaConf.create(incfg)
    return cfg

