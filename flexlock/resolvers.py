"""OmegaConf resolvers for FlexLock."""

from omegaconf import OmegaConf, DictConfig
from .data_hash import hash_data
from .load_stage import load_stage_from_path
from datetime import datetime
from contextlib import contextmanager
import re
from pathlib import Path
from functools import wraps
from . import config

# Resolvers whose evaluation is *deferred* to stage start (they read live
# filesystem/upstream-run state that only exists on the worker, not at submit
# time). During the submit-time freeze these are stubbed to re-emit their own
# call string (see ``deferred_stubbed``); everything else resolves eagerly.
DEFERRED_RESOLVERS = ("run_lock", "latest")

# Distinct "no default supplied" sentinel so that an explicit ``null`` default
# (e.g. ``${run_lock:${dir},key,null}``) is honoured rather than treated as
# "raise". ``None`` cannot serve as this marker because it is a valid default.
_MISSING = object()


def now_resolver(fmt: str = None) -> str:
    """
    OmegaConf resolver that returns the current time as a formatted string.

    Deprecated: prefer ``submit(..., save_dir_policy="timestamp")`` over
    embedding ``${now:}`` in ``save_dir``. See
    ``docs/resolution_simplification_plan.md``.

    Args:
        fmt: Format string for strftime (defaults to config.TIMESTAMP_FORMAT)
    """
    import warnings

    warnings.warn(
        "${now:} is deprecated; use save_dir_policy='timestamp' on submit()/run "
        "instead of embedding ${now:} in save_dir.",
        DeprecationWarning,
        stacklevel=2,
    )
    if fmt is None:
        fmt = config.TIMESTAMP_FORMAT
    return datetime.now().strftime(fmt)


def latest_resolver(path_glob: str, default=_MISSING) -> str:
    """
    OmegaConf resolver that returns the latest path matching the given pattern.

    Raises ``FileNotFoundError`` when nothing matches, unless a ``default`` is
    supplied (``${latest:pattern,fallback}``), in which case the default is
    returned. Returning the unmatched pattern silently — the old behaviour —
    produced a bogus path that failed far downstream.
    """
    from glob import glob
    import os

    # Expand user (~) and resolve the path
    path_glob = os.path.expanduser(path_glob)

    # Find all paths matching the pattern
    matching_paths = glob(path_glob, recursive=True)

    if not matching_paths:
        if default is not _MISSING:
            return default
        raise FileNotFoundError(
            f"latest resolver: no paths match pattern {path_glob!r}"
        )

    # Find the latest path by modification time
    latest_path = max(matching_paths, key=os.path.getmtime)

    return latest_path


def vinc_resolver(path: str, fmt: str = "_{i:04d}") -> str:
    """
    OmegaConf resolver that finds the highest existing version of a folder/file
    and returns the next versioned path as a string.

    The value is a pure function of the current filesystem state (highest
    existing version + 1) so that multiple references to the same ``${vinc:}``
    within one ``submit()`` resolve idempotently to the *same* directory — the
    counter only advances once the previous run's directory actually exists on
    disk.

    Concurrency note: because the claim is not taken here, two submits racing
    from separate processes can compute the same next version and collide.

    Deprecated: prefer ``submit(..., save_dir_policy="increment")``, which takes
    the atomic ``mkdir(exist_ok=False)`` claim at the right layer and so fixes
    the race this resolver could not. See ``docs/resolution_simplification_plan.md``.
    """
    import warnings

    warnings.warn(
        "${vinc:} is deprecated; use save_dir_policy='increment' on submit()/run "
        "instead of embedding ${vinc:} in save_dir. The policy also claims the "
        "directory atomically, fixing the concurrent-submit race.",
        DeprecationWarning,
        stacklevel=2,
    )
    from .save_dir import next_versioned_path

    return next_versioned_path(path, fmt)


def run_lock_resolver(run_dir: str, key: str, default=_MISSING):
    """
    OmegaConf resolver that reads a field from an upstream run.lock.

    Navigates a dot-separated key path into the run.lock YAML and returns
    the value with its native type (int, float, bool, str, list, dict).

    Usage in configs:
        ${run_lock:path/to/run_dir,config.datamodule.stats_file}
        ${run_lock:${run_dir},config.lit_module.regression_checkpoint_path,null}
    """
    from loguru import logger

    from .record import load_record

    data = load_record(run_dir)
    if data is None:
        if default is not _MISSING:
            logger.warning(f"run_lock resolver: no run.lock at {run_dir}, using default")
            return default
        raise FileNotFoundError(
            f"run_lock resolver: no run.lock found in {run_dir} "
            f"(nor a sweep-task record)"
        )

    # Navigate dot-path
    value = data
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            if default is not _MISSING:
                return default
            raise KeyError(
                f"run_lock resolver: key '{key}' not found in the run record at {run_dir} "
                f"(failed at '{part}')"
            )

    if value is None:
        # A legitimately null value is returned as-is when no default was
        # supplied; only substitute an explicitly provided default.
        return None if default is _MISSING else default
    return value


def register_resolvers():
    """
    Registers the flexlock resolvers with OmegaConf.
    """
    OmegaConf.register_new_resolver("now", now_resolver)
    OmegaConf.register_new_resolver("vinc", vinc_resolver)
    OmegaConf.register_new_resolver("latest", latest_resolver, use_cache=False)
    OmegaConf.register_new_resolver("run_lock", run_lock_resolver, use_cache=False)


# The real resolver implementations plus their registration options, so a stub
# context can faithfully restore them on exit.
def _real_resolvers():
    return {
        "now": (now_resolver, {}),
        "vinc": (vinc_resolver, {}),
        "latest": (latest_resolver, {"use_cache": False}),
        "run_lock": (run_lock_resolver, {"use_cache": False}),
    }


def _emit_stub_arg(value) -> str:
    """Render a (pre-resolved) resolver argument back into interpolation text.

    ``None`` becomes ``null`` so a real ``${run_lock:${dir},key,null}`` default
    survives the freeze; everything else is stringified as-is.
    """
    if value is None:
        return "null"
    return str(value)


@contextmanager
def _stubbed(names):
    """Temporarily replace the named resolvers with stubs that re-emit their own
    call string, with arguments already resolved by OmegaConf.

    OmegaConf resolves nested interpolations in a resolver's arguments *before*
    invoking the resolver. So under this context, resolving
    ``${run_lock:${precompute_dir},key}`` yields the frozen string
    ``${run_lock:/data/precomputed,key}`` — every non-stubbed interpolation
    (simple refs, cross-tree, multi-hop, mixed strings, relative refs) is
    resolved by OmegaConf itself, while the stubbed call collapses back to a
    self-contained call string with zero hand-rolled grammar parsing.

    Restores the real resolvers (with their original options) on exit.
    """
    def _make_stub(name):
        def _stub(*args):
            return "${" + name + ":" + ",".join(_emit_stub_arg(a) for a in args) + "}"
        return _stub

    reals = _real_resolvers()
    for name in names:
        OmegaConf.register_new_resolver(
            name, _make_stub(name), replace=True, use_cache=False
        )
    try:
        yield
    finally:
        for name in names:
            func, opts = reals[name]
            OmegaConf.register_new_resolver(name, func, replace=True, **opts)


def deferred_stubbed():
    """Stub only the deferred resolvers (``run_lock``/``latest``).

    Used by the merge-before-resolve sweep freeze, where ``vinc``/``now`` should
    still fire (they are being retired via ``save_dir_policy``).
    """
    return _stubbed(DEFERRED_RESOLVERS)


def frozen_resolvers():
    """Stub every flexlock resolver, so all ``${name:args}`` calls are preserved
    as frozen call strings during the submit-time node freeze.
    """
    return _stubbed(tuple(_real_resolvers().keys()))


def resolve_deferred(cfg: DictConfig) -> DictConfig:
    """Fire the deferred resolvers once, at stage start, and return a detached
    config of concrete values.

    This is the single point where ``run_lock``/``latest`` (and any other
    interpolations left after the submit-time freeze) are evaluated with the
    real resolvers. Called on the worker right after the task override is merged
    (and on the local single-run path). Re-wrapping as a plain config detaches
    it from any parent so downstream ``config.copy()`` cannot re-fire anything.
    """
    resolved = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=False)
    return OmegaConf.create(_escape_literals(resolved))


def _escape_literals(value):
    """Re-escape ``${`` in already-resolved values before re-wrapping.

    After a full resolve, a string can only still contain ``${`` if it was an
    escaped literal (backslash-escaped interpolation) or a resolver's output. Re-wrapping it in a
    fresh config would turn it back into a live interpolation, so escape it.
    """
    if isinstance(value, str):
        return value.replace("${", "\\${") if "${" in value else value
    if isinstance(value, dict):
        return {k: _escape_literals(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_escape_literals(v) for v in value]
    return value
