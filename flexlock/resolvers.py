from omegaconf import OmegaConf, DictConfig
from .data_hash import hash_data
from .load_stage import load_stage_from_path
from datetime import datetime
import re
from pathlib import Path
from contextlib import contextmanager
import threading
from functools import wraps

# Thread-local storage for resolver cache during execution context
_resolver_context = threading.local()

def init_resolver_context():
    """Initialize resolver context for current execution."""
    _resolver_context.cache = {}

def clear_resolver_context():
    """Clear resolver context after execution."""
    if hasattr(_resolver_context, 'cache'):
        del _resolver_context.cache

def get_resolver_cache():
    """Get current execution's resolver cache."""
    if not hasattr(_resolver_context, 'cache'):
        _resolver_context.cache = {}
    return _resolver_context.cache

def cached_resolver(func):
    """Decorator that caches resolver results within a single execution."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get current execution's cache
        cache = get_resolver_cache()
        
        # Create a cache key from the function name and parameters
        # Convert args and kwargs to a hashable representation
        try:
            cache_key = (func.__name__, args, tuple(sorted(kwargs.items())) if kwargs else ())
        except TypeError:
            # If args/kwargs are not hashable, call without caching
            return func(*args, **kwargs)
        
        # Return cached result if available
        if cache_key in cache:
            return cache[cache_key]
        
        # Call the original function and cache the result
        result = func(*args, **kwargs)
        cache[cache_key] = result
        return result
    return wrapper

@contextmanager
def resolver_context():
    """Context manager that ensures resolver caching within execution."""
    init_resolver_context()
    try:
        yield
    finally:
        clear_resolver_context()

@cached_resolver
def track_resolver(path: str) -> str:
    """
    OmegaConf resolver that computes and returns the hash of a data path.
    """
    return hash_data(path)

@cached_resolver
def stage_resolver(path: str) -> dict:
    """
    OmegaConf resolver that loads a previous stage's run.lock and returns its content.
    """
    return load_stage_from_path(path)

@cached_resolver
def now_resolver(fmt: str = "%Y-%m-%d_%H-%M-%S") -> str:
    """
    OmegaConf resolver that returns the current time as a formatted string.
    """
    return datetime.now().strftime(fmt)

@cached_resolver
def vinc_resolver(path: str, fmt: str = '_{i:04d}') -> str:
    """
    OmegaConf resolver that finds the highest existing version of a folder/file 
    and returns the next versioned path as a string. Results are cached to ensure
    consistent values within a single execution.
    """
    # Compute the result (original logic)
    p = Path(path)
    parent_dir = p.parent
    base_name = p.name

    regex_pattern = re.sub(r'\{i.*\}', r'(\\d+)', fmt)
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

@cached_resolver
def snapshot_resolver(path: str, key: str | None = None, *, _root_: DictConfig) -> str:
    """
    OmegaConf resolver that adds a path to the snapshot's data and prevs sections.
    """
    from .snapshot import snapshot
    
    item = path if key is None else {key: path}
    
    # The _root_ config is passed by OmegaConf to the resolver.
    # We can use it to call snapshot with the actual config.
    snapshot(config=_root_, data=item, prevs=[path], merge=True, mlflowlink=False, resolve=False)
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
