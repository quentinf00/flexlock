from omegaconf import OmegaConf, DictConfig
from .data_hash import hash_data
from .load_stage import load_stage_from_path
from datetime import datetime
import re
from pathlib import Path

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

def now_resolver(fmt: str = "%Y-%m-%d_%H-%M-%S") -> str:
    """
    OmegaConf resolver that returns the current time as a formatted string.
    """
    return datetime.now().strftime(fmt)

def vinc_resolver(path: str, fmt: str = '_{i:04d}') -> str:
    """
    OmegaConf resolver that finds the highest existing version of a folder/file 
    and returns the next versioned path as a string.
    """
    p = Path(path)
    parent_dir = p.parent
    base_name = p.name


    regex_pattern = re.sub(r'\{i.*\}', r'(\\d+)', fmt)
    regex = re.compile(f"^{re.escape(base_name)}{regex_pattern}")

    highest_version = -1
    if not parent_dir.exists():
        parent_dir.mkdir(parents=True, exist_ok=True)
    print(parent_dir, base_name, regex)
    for item in parent_dir.glob(f"{base_name}*"):
        print(item)
        match = regex.match(item.name)
        print(match)
        if match:
            version = int(match.group(1))
            if version > highest_version:
                highest_version = version

    next_version = highest_version + 1
    version_str = fmt.format(i=next_version)
    
    return str(parent_dir / f"{base_name}{version_str}")

def snapshot_resolver(path: str, key: str = None, *, _root_: DictConfig) -> str:
    """
    OmegaConf resolver that adds a path to the snapshot's data and prevs sections.
    """
    from .snapshot import snapshot
    
    item = path if key is None else {key: path}
    
    # The _root_ config is passed by OmegaConf to the resolver.
    # We can use it to call snapshot with the actual config.
    snapshot(config=_root_, data=item, prevs=item, merge=True, mlflowlink=False, resolve=False)
    return path

def register_resolvers():
    """
    Registers the flexlock resolvers with OmegaConf.
    """
    OmegaConf.register_new_resolver("track", track_resolver)
    OmegaConf.register_new_resolver("stage", stage_resolver)
    OmegaConf.register_new_resolver("now", now_resolver)
    OmegaConf.register_new_resolver("vinc", vinc_resolver)
    OmegaConf.register_new_resolver("snapshot", snapshot_resolver)
