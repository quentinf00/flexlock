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

# select_and_freeze_root_refs moved to flexlock.freeze; re-exported here for the
# existing import sites (api.py, runner.py, tests) that import it from utils.
from .freeze import select_and_freeze_root_refs  # noqa: F401


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


def collect_task_repos(cfg, tasks, task_to=None) -> Dict:
    """Repos to record in a sweep master's run.lock, including the tasks' own.

    ``extract_tracking_info(cfg)`` only sees the base config. When ``_target_``
    (or ``_snapshot_.repos``) lives in the tasks instead (a single HPC run, or
    ``--sweep-file`` of full configs), the base yields nothing, and since
    workers record tasks as deltas against the master, no code state would be
    recorded at all. Tasks are grouped by their ``_target_``/``_snapshot_``
    so the cost is one merge per distinct target, not per task.
    """
    repos, _, _ = extract_tracking_info(cfg)
    seen = set()
    for task in tasks:
        node = task
        if task_to and isinstance(task, (dict, DictConfig)):
            node = OmegaConf.select(OmegaConf.create(task), task_to)
        if not isinstance(node, (dict, DictConfig)):
            continue
        target = node.get("_target_")
        snap = node.get("_snapshot_")
        if target is None and snap is None:
            continue
        key = (str(target), str(snap))
        if key in seen:
            continue
        seen.add(key)
        try:
            task_repos, _, _ = extract_tracking_info(
                merge_task_into_cfg(cfg, task, task_to)
            )
        except Exception as exc:
            logger.debug(f"Could not extract repos from task {target}: {exc}")
            continue
        for name, info in task_repos.items():
            repos.setdefault(name, info)
    return repos


def _find_run_dir(start_path: str) -> str | None:
    """Walk up from a path to the nearest run dir (run.lock or task marker)."""
    from .record import find_run_dir

    return find_run_dir(start_path)


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

    # If the module is __main__ the _target_ won't import correctly in a
    # Slurm/PBS worker or any subprocess that doesn't run the user's script
    # as the entry point.  Try to resolve the real dotted module path from the
    # file's location relative to CWD (which run_cli adds to sys.path).
    if target.startswith("__main__."):
        try:
            file_path = Path(inspect.getfile(obj)).resolve()
            module_name = str(
                file_path.relative_to(Path.cwd().resolve()).with_suffix("")
            ).replace("/", ".").replace("\\", ".")
            target = f"{module_name}.{obj.__qualname__}"
            logger.debug(f"py2cfg: resolved __main__ to '{target}'")
        except (TypeError, ValueError, OSError):
            logger.warning(
                f"py2cfg: _target_ is '{target}'. This won't import correctly in a "
                f"Slurm/PBS worker. Run your script as a module "
                f"('python -m your.module') instead of 'python script.py' to get a "
                f"stable importable _target_."
            )

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


def parse_sweep_string(sweep_str: str) -> list:
    """Parse a comma-separated CLI sweep value into a list.

    Examples::

        parse_sweep_string("1,2,3")              # → [1, 2, 3]
        parse_sweep_string("lr=0.1,lr=0.2")      # → [{'lr': 0.1}, {'lr': 0.2}]
        parse_sweep_string('"a,b",c')            # → ['a,b', 'c']
    """
    import csv
    import yaml as _yaml

    reader = csv.reader([sweep_str], skipinitialspace=True)
    items = next(reader)
    out = []
    for item in items:
        if "=" in item:
            try:
                conf = OmegaConf.from_dotlist([item])
                out.append(OmegaConf.to_container(conf))
            except Exception:
                out.append(item)
        else:
            try:
                out.append(_yaml.safe_load(item))
            except Exception:
                out.append(item)
    return out


def _load_one_sweep_file(fpath: Path) -> list:
    """Load a single sweep file and return its contents as a list of tasks.

    YAML/JSON files that contain a list are expanded in-place; a single dict
    is wrapped in a one-element list.  Plain text files treat each non-empty
    line as one task value.

    Interpolation strings (``${...}``) are intentionally preserved as raw
    strings so that deferred resolvers (``${run_lock:}``/``${latest:}``) fire at
    execution time on the worker rather than at sweep-loading time.
    """
    import json as _json
    import yaml as _yaml
    from .exceptions import FlexLockConfigError

    if not fpath.exists():
        raise FlexLockConfigError(f"Sweep file '{fpath}' not found.")
    if fpath.suffix in (".yaml", ".yml"):
        raw = _yaml.safe_load(fpath.read_text())
    elif fpath.suffix == ".json":
        with open(fpath) as f:
            raw = _json.load(f)
    else:
        raw = [_yaml.safe_load(line.strip()) for line in fpath.read_text().splitlines() if line.strip()]
    if raw is None:
        return []
    return raw if isinstance(raw, list) else [raw]


def load_sweep(
    *,
    sweep: "list | str | None" = None,
    sweep_file: "str | Path | list[str | Path] | None" = None,
    sweep_key: "str | None" = None,
    root_cfg: "DictConfig | None" = None,
) -> list:
    """Load a sweep list from one of several sources.

    Exactly one source must be provided. Returns the parsed sweep list. If
    the source yields a single value or dict, it is wrapped in a list.

    Args:
        sweep: A pre-built list, or a CLI-style comma-separated string.
        sweep_file: Path (or list of paths) to .yaml/.yml, .json, or text
            files.  When a list is given, each file is loaded independently
            and results are concatenated.  A file containing a single dict
            is treated as one task; a file containing a list expands into
            multiple tasks.
        sweep_key: Dotted key into ``root_cfg`` whose value is the sweep list.
        root_cfg: Required when ``sweep_key`` is used.
    """
    import yaml as _yaml
    from .exceptions import FlexLockValidationError, FlexLockConfigError

    sources = sum(x is not None for x in (sweep, sweep_file, sweep_key))
    if sources > 1:
        raise FlexLockValidationError(
            "Multiple sweep sources provided. Use only ONE of "
            "`sweep`, `sweep_file`, or `sweep_key`."
        )
    if sources == 0:
        return []

    if sweep is not None:
        raw = parse_sweep_string(sweep) if isinstance(sweep, str) else sweep
    elif sweep_file is not None:
        # Normalise to a list of Path objects.
        if isinstance(sweep_file, (str, Path)):
            files = [Path(sweep_file)]
        else:
            files = [Path(f) for f in sweep_file]
        raw = []
        for f in files:
            raw.extend(_load_one_sweep_file(f))
    else:  # sweep_key
        if root_cfg is None:
            raise FlexLockValidationError(
                "sweep_key requires root_cfg to look up the value."
            )
        node = OmegaConf.select(root_cfg, sweep_key)
        if node is None:
            raise FlexLockValidationError(
                f"Sweep key '{sweep_key}' not found in config."
            )
        raw = OmegaConf.to_container(node, resolve=True) if isinstance(
            node, (DictConfig, ListConfig)
        ) else node

    if raw is None:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    return raw


def load_python_defaults(import_path: str):
    """Dynamically import a module or file path to retrieve a variable.

    Accepted forms:

    - ``'pkg.config.defaults'`` — dotted module path, variable is the last
      segment.
    - ``'pkg.config:defaults'`` — module + colon-separated variable name.
    - ``'configs/defaults.py:defaults'`` — file path + colon-separated
      variable name.
    - ``'configs/defaults.py'`` — bare file path, variable defaults to
      ``defaults`` by convention.
    """
    # Bare file path: auto-append ":defaults" so users don't need to spell
    # the conventional variable name.
    if ":" not in import_path and (
        import_path.endswith(".py") or Path(import_path).is_file()
    ):
        import_path = f"{import_path}:defaults"

    if ":" in import_path:
        path_str, var_name = import_path.split(":", 1)
        file_path = Path(path_str)
        if not file_path.exists():
            # A slashed left side that doesn't resolve to a file is almost
            # always a typo — surface a clear hint instead of letting
            # importlib.import_module mangle it.
            if "/" in path_str:
                from .exceptions import FlexLockConfigError

                raise FlexLockConfigError(
                    f"'{path_str}' does not exist. For file-based "
                    f"defaults, use 'path/to/file.py:variable' (or just "
                    f"'path/to/file.py' to default to the 'defaults' "
                    f"variable)."
                )
            # Otherwise treat the left side as a dotted module name.
            module = importlib.import_module(path_str)
            return getattr(module, var_name)
        # Load file under its real stem and register in sys.modules so any
        # `_target_: <stem>.fn` captured by py2cfg in that file remains
        # importable later (during instantiate()). Also make sibling
        # imports work by ensuring the parent dir is on sys.path.
        file_path = file_path.resolve()
        module_name = file_path.stem
        parent_dir = str(file_path.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return getattr(module, var_name)

    # Dotted module: "pkg.config.defaults" — module is "pkg.config", var is "defaults".
    # If the left part looks like a filesystem path (contains '/'), the user
    # almost certainly meant a file — surface a clear hint instead of letting
    # importlib's mangled error bubble up.
    if "/" in import_path:
        from .exceptions import FlexLockConfigError

        raise FlexLockConfigError(
            f"'{import_path}' looks like a file path but does not exist and "
            f"has no colon-separated variable name. For file-based defaults, "
            f"use 'path/to/file.py:variable' (or just 'path/to/file.py' to "
            f"default to the 'defaults' variable)."
        )
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
    r"""
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

    # config is a dict — never mutate the caller's object. Copy before
    # stripping the tracking-only "_snapshot_"/"_preset_" keys so the
    # original keeps them.
    reserved = [k for k in ("_snapshot_", "_preset_") if k in config]
    if reserved:
        if isinstance(config, DictConfig):
            config = config.copy()
            with open_dict(config):
                for k in reserved:
                    del config[k]
        else:
            config = dict(config)
            for k in reserved:
                del config[k]

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


def enqueue_to_file(path: "str | Path", cfg_dict: dict) -> int:
    """Atomically append *cfg_dict* to a YAML list file and return the new queue length.

    The file is created if it does not exist.  Existing content must be a YAML
    list (or an empty file).  The write is atomic: a temporary sibling file is
    written first, then renamed over the target so partial writes are never
    visible to concurrent readers.

    Args:
        path: Destination YAML file (created if absent).
        cfg_dict: A plain Python dict (no OmegaConf nodes) to append.

    Returns:
        Number of items in the queue after appending.
    """
    import tempfile, os
    import yaml as _yaml

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: list = []
    if path.exists() and path.stat().st_size > 0:
        data = _yaml.safe_load(path.read_text())
        if data is None:
            existing = []
        elif isinstance(data, list):
            existing = data
        else:
            raise ValueError(
                f"Queue file '{path}' must contain a YAML list, got {type(data).__name__}."
            )

    existing.append(cfg_dict)

    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp-", suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            _yaml.safe_dump(existing, f, default_flow_style=False, allow_unicode=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    return len(existing)
