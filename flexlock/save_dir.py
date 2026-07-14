"""Explicit save_dir policies: naming + collision guard.

This module replaces the ``${vinc:}``/``${now:}`` resolver mechanism. Configs
keep a **stable** ``save_dir``; what happens when that directory is already
occupied by a previous run is decided once, explicitly, at submit time.

A directory is *occupied* when it contains a ``run.lock`` (written before
execution starts). ``run.complete`` marks a finished run; a ``run.lock``
without it is a crashed or in-flight run.

Policies:

- ``"raise"`` (the default): refuse to run into an occupied directory.
- ``"increment"`` / ``"timestamp"``: naming policies — derive a fresh
  directory from the configured base, so collisions can't happen.
- ``"overwrite"``: delete the occupied directory's contents, then run.
- ``"skip"``: don't execute; return the occupant's result (must be complete).
- ``"unsafe"``: run in place with no check (pre-0.8 behaviour).

Binding time: ``save_dir`` creation. See ``docs/resolution_simplification_plan.md``.
"""

import re
import shutil
from pathlib import Path

from omegaconf import DictConfig, open_dict

from . import config
from .run_record import COMPLETE_MARKER, LOCK_NAME

GUARD_POLICIES = ("raise", "overwrite", "skip", "unsafe")
NAMING_POLICIES = ("increment", "timestamp")

# Outcomes of apply_save_dir_policy
RUN = "run"
SKIP = "skip"


def next_versioned_path(path: str, fmt: str = "_{i:04d}") -> str:
    """Return the next unclaimed versioned path for ``path``.

    Scans ``path``'s parent for existing entries matching ``<name><fmt>`` and
    returns ``<name>`` suffixed with the next integer. This is a *pure function
    of the current filesystem state* (highest existing version + 1); it does not
    create or claim the returned directory.

    Args:
        path: Base path (``outputs/run``) to version.
        fmt: Suffix format with an ``{i}`` field (``"_{i:04d}"`` → ``_0000``).
    """
    p = Path(path)
    parent_dir = p.parent
    base_name = p.name

    regex_pattern = re.sub(r"\{i.*\}", r"(\\d+)", fmt)
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


def resolve_save_dir(cfg: DictConfig) -> None:
    """Bake ``cfg.save_dir`` down to a plain string, in place.

    Forces any interpolation to resolve so the value is stable across later
    reads (snapshot vs. complete marker). The access can raise when the value
    carries an interpolation unresolvable in this config's scope (e.g. a
    sub-config passed in isolation with ``save_dir: ${save_dir}/features``, or
    a sweep base with a per-item ``${.variable}``); leave it unresolved then.
    """
    if "save_dir" not in cfg:
        return
    try:
        if cfg.save_dir is not None:
            with open_dict(cfg):
                cfg.save_dir = str(cfg.save_dir)
    except Exception:
        pass


def is_occupied(save_dir: "str | Path") -> bool:
    """True when ``save_dir`` holds a ``run.lock`` (a previous run lives here)."""
    return (Path(save_dir) / LOCK_NAME).exists()


def is_complete(save_dir: "str | Path") -> bool:
    """True when ``save_dir`` holds both ``run.lock`` and ``run.complete``."""
    d = Path(save_dir)
    return (d / LOCK_NAME).exists() and (d / COMPLETE_MARKER).exists()


def validate_policy(policy: "str | None") -> None:
    """Raise ``FlexLockValidationError`` on an unknown policy name."""
    from .exceptions import FlexLockValidationError

    if policy is not None and policy not in GUARD_POLICIES + NAMING_POLICIES:
        raise FlexLockValidationError(
            f"Unknown save_dir_policy {policy!r}; expected one of "
            f"{', '.join(GUARD_POLICIES + NAMING_POLICIES)} (or None = 'raise')."
        )


def clean_run_dir(save_dir: "str | Path") -> None:
    """Delete the contents of an occupied run directory (keep the dir itself)."""
    for entry in Path(save_dir).iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def occupied_error(save_dir: str, sweep_item: "int | None" = None):
    """Build the FlexLockValidationError for the default 'raise' guard."""
    from .exceptions import FlexLockValidationError

    what = "a run" if sweep_item is None else f"a run (sweep item {sweep_item})"
    return FlexLockValidationError(
        f"save_dir {save_dir!r} already contains {what} ({LOCK_NAME} present"
        f"{', complete' if is_complete(save_dir) else ', incomplete'}). "
        f"Refusing to run into it (save_dir_policy='raise' is the default). "
        f"Options: force=True / --force (rerun in place), or save_dir_policy="
        f"'increment' (fresh versioned dir), 'overwrite' (clean then run), "
        f"'skip' (reuse the existing result), 'unsafe' (no guard)."
    )


def apply_save_dir_policy(
    cfg: DictConfig,
    policy: "str | None",
    force: bool = False,
) -> str:
    """Apply the save_dir policy once, in place; say whether to run.

    Naming policies (``increment``/``timestamp``) rewrite ``cfg.save_dir`` to
    a fresh directory — ``increment`` **atomically claims** it with
    ``mkdir(exist_ok=False)`` + retry, fixing the concurrent-submit race the
    old ``${vinc:}`` resolver could not.

    Guard policies decide what to do when ``cfg.save_dir`` is occupied
    (contains ``run.lock``):

    - ``None`` / ``"raise"``: raise ``FlexLockValidationError`` — unless
      ``force=True`` (explicit in-place rerun).
    - ``"overwrite"``: delete the directory's contents. Only fires on an
      *occupied* dir — a mistyped ``save_dir`` pointing at a plain data
      directory (no ``run.lock``) is never wiped.
    - ``"skip"``: return :data:`SKIP` if the occupant is complete; raise if it
      is a crashed/in-flight run (there is no result to return).
    - ``"unsafe"``: no check.

    Sweeps don't use this guard path — items are guarded individually in
    ``_submit_sweep`` after the per-item cache check (where ``skip`` means
    resume). Only the naming policies apply here to a sweep root.

    Returns:
        :data:`RUN` to proceed with execution, :data:`SKIP` when the caller
        should return the occupant's cached result instead.
    """
    from .exceptions import FlexLockValidationError

    validate_policy(policy)

    resolve_save_dir(cfg)
    if "save_dir" not in cfg or cfg.get("save_dir") is None:
        return RUN

    base = str(cfg.save_dir)

    if policy == "timestamp":
        from datetime import datetime

        ts = datetime.now().strftime(config.TIMESTAMP_FORMAT)
        with open_dict(cfg):
            cfg.save_dir = str(Path(base) / ts)
        return RUN

    if policy == "increment":
        # Compute the next version, then claim it atomically. On collision
        # (another submit claimed it first) recompute and retry.
        for _ in range(1000):
            candidate = next_versioned_path(base)
            try:
                Path(candidate).mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                continue
            with open_dict(cfg):
                cfg.save_dir = candidate
            return RUN
        raise RuntimeError(
            f"apply_save_dir_policy: could not claim an incremented save_dir "
            f"under {base!r} after 1000 attempts."
        )

    # Guard policies from here on.
    if policy == "unsafe":
        return RUN

    if not is_occupied(base):
        return RUN

    if policy == "overwrite":
        clean_run_dir(base)
        return RUN

    if policy == "skip":
        if is_complete(base):
            return SKIP
        raise FlexLockValidationError(
            f"save_dir_policy='skip': {base!r} holds an incomplete run "
            f"({LOCK_NAME} without {COMPLETE_MARKER}) — no result to return. "
            f"Re-run with force=True or save_dir_policy='overwrite'."
        )

    # policy in (None, "raise")
    if force:
        # Explicit in-place rerun: run.complete was already invalidated by
        # the caller; keep outputs and run.lock, let the run overwrite.
        return RUN
    raise occupied_error(base)
