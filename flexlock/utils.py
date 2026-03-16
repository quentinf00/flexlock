"""Utility functions for FlexLock."""

import inspect
import importlib
import sys
import functools
from pathlib import Path
from typing import Any, Tuple, Dict, List
from omegaconf import OmegaConf, DictConfig, ListConfig, open_dict
from dataclasses import is_dataclass
from contextlib import contextmanager
from loguru import logger
import warnings
from dataclasses import fields


def collect_target_include_patterns(cfg, repo_path=None):
    """
    Recursively walk a config, collect all _target_ values, resolve them to
    source file paths relative to the repo root. Returns a list of relative
    file paths suitable for use as match_include patterns in smart_run.

    External targets (site-packages, builtins) are silently skipped.
    """
    import os

    targets = set()
    _walk_targets(cfg, targets)

    if not targets:
        return []

    patterns = []
    for target_str in targets:
        try:
            module_name, _ = target_str.rsplit(".", 1)
            mod = importlib.import_module(module_name)
            source = inspect.getfile(mod)

            if repo_path is None:
                repo_path = resolve_module_to_repo_path(module_name)

            rel = os.path.relpath(source, repo_path)
            # Skip if outside the repo (e.g. ../site-packages/...)
            if rel.startswith(".."):
                continue
            patterns.append(rel)
        except Exception:
            continue

    return sorted(set(patterns))


def _walk_targets(cfg, out):
    """Recursively collect _target_ strings from a nested config."""
    if isinstance(cfg, (dict, DictConfig)):
        for key, val in cfg.items():
            if key == "_snapshot_":
                continue
            if key == "_target_" and isinstance(val, str):
                out.add(val)
            else:
                _walk_targets(val, out)
    elif isinstance(cfg, (list, ListConfig)):
        for item in cfg:
            _walk_targets(item, out)


def resolve_module_to_repo_path(module_name: str) -> str:
    """Resolve a Python module name to its containing git repository's working directory."""
    mod = importlib.import_module(module_name)
    source_file = inspect.getfile(mod)
    from git.repo import Repo as GitRepo

    repo_obj = GitRepo(source_file, search_parent_directories=True)
    return repo_obj.working_tree_dir


def extract_tracking_info(cfg) -> Tuple[Dict, Dict, List]:
    """
    Extract tracking information from config's _snapshot_ field.

    This is a unified function used across FlexLock to extract repository
    tracking, data hashing, and lineage information from configurations.

    If no repos.main is specified but the config has a _target_, automatically
    detects the git repository of the target function's source file.

    Args:
        cfg: OmegaConf DictConfig with optional _snapshot_ field

    Returns:
        tuple: (repos, data, prevs) where:
            - repos: dict of {name: {"path": str, "include": list|None, "exclude": list|None}}
            - data: dict of {name: path} for data files/dirs to hash
            - prevs: list of paths to check for upstream FlexLock runs

    Raises:
        FlexLockConfigError: If _snapshot_ contains invalid keys like 'repo' (singular)

    Examples:
        >>> cfg = OmegaConf.create({
        ...     '_snapshot_': {
        ...         'repos': {'main': '.'},
        ...         'data': {'input': 'data/train.csv'}
        ...     }
        ... })
        >>> repos, data, prevs = extract_tracking_info(cfg)
        >>> repos
        {'main': {'path': '.'}}
    """
    from .exceptions import FlexLockConfigError

    repos = {}
    data = {}
    prevs = []

    if "_snapshot_" in cfg:
        snap_cfg = cfg._snapshot_

        # Extract repos (only plural supported)
        if "repos" in snap_cfg:
            repos_container = OmegaConf.to_container(snap_cfg.repos, resolve=True)
            for name, val in repos_container.items():
                if isinstance(val, str):
                    repos[name] = {"path": val}
                elif isinstance(val, dict):
                    has_path = "path" in val
                    has_module = "module" in val

                    if not has_path and not has_module:
                        raise FlexLockConfigError(
                            f"Repo '{name}' must specify either 'path' or 'module'."
                        )

                    if has_module and not has_path:
                        try:
                            resolved_path = resolve_module_to_repo_path(val["module"])
                        except Exception as e:
                            raise FlexLockConfigError(
                                f"Repo '{name}': could not resolve module '{val['module']}': {e}"
                            )
                        repos[name] = {
                            "path": resolved_path,
                            "module": val["module"],
                            "include": val.get("include"),
                            "exclude": val.get("exclude"),
                        }
                    else:
                        repos[name] = {
                            "path": val["path"],
                            "module": val.get("module"),
                            "include": val.get("include"),
                            "exclude": val.get("exclude"),
                        }
                else:
                    raise FlexLockConfigError(
                        f"Repo '{name}' value must be a string (path) or dict. Got: {type(val)}"
                    )
        elif "repo" in snap_cfg:
            raise FlexLockConfigError(
                "Found 'repo' (singular) in _snapshot_ configuration. "
                "Please use 'repos' (plural) instead. "
                "Example: _snapshot_={'repos': {'main': '.'}}"
            )

        # Extract data
        if "data" in snap_cfg:
            data_raw = snap_cfg.data
            if not isinstance(data_raw, (dict, DictConfig)):
                raise FlexLockConfigError(
                    "snapshot's data should be a mapping"
                    "Example: _snapshot_={'data': {'dataset': 'data/dataset.csv'}}"
                )
            data = OmegaConf.to_container(data_raw, resolve=True)

        # Extract prevs (lineage paths)
        if "prevs" in snap_cfg:
            prevs_raw = snap_cfg.prevs
            if not isinstance(prevs_raw, (list, ListConfig)):
                raise FlexLockConfigError(
                    "snapshot's prevs should be a list"
                    "Example: _snapshot_={'prevs': ['path/to/run/toto']}"
                )
            prevs = OmegaConf.to_container(prevs_raw, resolve=True)

    # Auto-populate repo from _target_ using top-level module name
    if "_target_" in cfg:
        try:
            target_str = (
                cfg._target_ if isinstance(cfg, DictConfig) else cfg["_target_"]
            )
            top_level_module = target_str.split(".")[0]
            if top_level_module not in repos:
                module_name, _ = target_str.rsplit(".", 1)
                resolved_path = resolve_module_to_repo_path(module_name)
                repos[top_level_module] = {
                    "path": resolved_path,
                    "module": top_level_module,
                }
                logger.debug(
                    f"Auto-populated repos['{top_level_module}'] from _target_ '{target_str}': {resolved_path}"
                )
        except Exception:
            logger.debug(
                "Could not auto-populate repo from _target_ (REPL or built-in?)"
            )

    # "prevs_from_data": Walk up from each data path to find the nearest
    # run.lock, resolving data files to their containing flexlock run dir.
    # This way snapshot() receives clean directory paths, not raw file paths.
    for data_path in data.values():
        run_dir = _find_run_dir(data_path)
        if run_dir and run_dir not in prevs:
            prevs.append(run_dir)

    return repos, data, prevs


def _find_run_dir(start_path: str) -> str | None:
    """Walk up from a path to find the nearest directory containing run.lock."""
    p = Path(start_path)
    if p.is_file():
        p = p.parent
    # Walk up, but stop at filesystem root
    while p != p.parent:
        if (p / "run.lock").exists():
            return str(p)
        p = p.parent
    return None


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


def py2cfg(obj, /, *pos, **overrides):
    """
    Generates a default configuration dict from a function or class signature.
    Supports nested py2cfg calls and handles decorated functions.
    """
    # 1. Unwrap decorated functions
    if hasattr(obj, "_original_fn"):
        obj = obj._original_fn

    # 1. Handle functools.partial
    # If it's a partial, we unwrap it, capture the fixed args, and mark as _partial_
    if isinstance(obj, functools.partial):
        config = py2cfg(obj.func)
        config["_partial_"] = True
        # Add positional arguments as _args_ if they exist
        if obj.args:
            config["_args_"] = list(obj.args)
        config.update(obj.keywords)  # Add bound keyword arguments
        config.update(overrides)  # Apply runtime overrides
        return config

    # 2. Determine target and signature source
    if inspect.isclass(obj):
        target = f"{obj.__module__}.{obj.__qualname__}"
        sig_obj = obj.__init__
    elif inspect.isroutine(obj):
        target = f"{obj.__module__}.{obj.__qualname__}"
        sig_obj = obj
    else:
        raise ValueError(f"py2cfg expects class or function, got {type(obj)}")

    # 3. Build Config
    config = {"_target_": target}

    try:
        sig = inspect.signature(sig_obj)
        params = list(sig.parameters.values())

        # Skip 'self' for classes or bound methods
        if inspect.isclass(obj) or (
            hasattr(sig_obj, "__self__") and sig_obj.__name__ != "__init__"
        ):
            if params and params[0].name == "self":
                params = params[1:]

        for param in params:
            if param.default is not param.empty:
                # We generally only capture primitive defaults here.
                # Complex defaults (classes) should be handled via explicit overrides
                # or None defaults in the function signature.
                val = param.default
                # If a default value is itself a class/function, convert it too.
                if inspect.isclass(val) or inspect.isfunction(val):
                    try:
                        val = py2cfg(val)
                    except ValueError:
                        pass  # Keep original if conversion fails
                config[param.name] = val
    except (ValueError, TypeError):
        pass

    # 4. Apply overrides (nested py2cfg calls happen here)
    config.update(overrides)

    if len(pos) > 0:
        config.update(
            OmegaConf.create(dict(_args_=list(pos)))
        )  # Add positional arguments if any

    return OmegaConf.create(config)


def load_python_defaults(import_path: str):
    """Dynamically imports a module or file path to retrieve 'defaults'."""
    if ":" in import_path:
        # Path based: "configs/my_conf.py:defaults"
        path_str, var_name = import_path.split(":")
        file_path = Path(path_str).resolve()
        spec = importlib.util.spec_from_file_location("dynamic_defaults", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, var_name)
    else:
        # Module based: "pkg.config.defaults"
        module_name, var_name = import_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, var_name)


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
        \*args, \*\*kwargs: Additional arguments to pass to the root object.
    """
    # 1. Base case: If config is not a dict or list, return it as is.
    logger.debug(f"Instantiating config: {config} of type {type(config)}")
    if not isinstance(config, (dict, list, DictConfig, ListConfig)):
        logger.debug(f"Returning primitive config: {config}")
        return config

    if isinstance(config, (list, ListConfig)):
        return [instantiate(item) for item in config]

    # config is a dict
    if "_snapshot_" in config:
        with open_dict(config):
            del config["_snapshot_"]

    # 2. Check if this dict represents a target object
    if "_target_" not in config:
        # It's just a regular dictionary, but we should check values recursively
        return {k: instantiate(v) for k, v in config.items()}

    # 3. Prepare the configuration
    # Copy to avoid mutating the original dict
    conf_copy = config.copy()
    target_path = conf_copy.pop("_target_")

    # Handle positional arguments
    config_args = conf_copy.pop("_args_", [])
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

    # 6. Combine positional arguments
    # First config args, then runtime args
    all_args = instantiate(config_args) + list(args)

    # 7. Instantiate or return partial
    if is_partial:
        return functools.partial(target_class, *all_args, **init_args)

    return target_class(*all_args, **init_args)
