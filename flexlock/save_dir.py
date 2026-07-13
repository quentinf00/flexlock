"""Explicit save_dir naming policies.

This module replaces the ``${vinc:}``/``${now:}`` resolver mechanism for
producing a run directory. Instead of hiding the "create a fresh directory"
side effect inside config interpolation (which fires at unpredictable read
times and cannot claim the directory atomically), the policy is applied once,
explicitly, at submit time.

Binding time: ``save_dir`` creation. See ``docs/resolution_simplification_plan.md``.
"""

import re
from pathlib import Path

from omegaconf import DictConfig, open_dict

from . import config


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


def apply_save_dir_policy(cfg: DictConfig, policy: "str | None") -> None:
    """Resolve ``cfg.save_dir`` to a concrete string exactly once, in place.

    ``policy`` selects how the final directory name is derived from the
    configured ``save_dir``:

    - ``None``: resolve the configured value as-is (current behaviour).
    - ``"increment"``: version the base with :func:`next_versioned_path` and
      **atomically claim** the result with ``mkdir(exist_ok=False)``, retrying
      on collision. This fixes the concurrent-submit race that the old
      ``${vinc:}`` resolver could not: two processes computing the same next
      version now can't both win — the loser retries and gets the next slot.
    - ``"timestamp"``: ``base / now.strftime(config.TIMESTAMP_FORMAT)``.

    No-op when the config has no ``save_dir`` key or it is ``None``.
    """
    if "save_dir" not in cfg:
        return

    if policy is None:
        # Resolve as-is: force any interpolation to bake down to a string so
        # the value is stable across later reads (snapshot vs. complete marker).
        # The ``save_dir`` access itself can raise when it carries an
        # interpolation unresolvable in this config's scope (e.g. a sub-config
        # passed in isolation with save_dir: ${save_dir}/features, or a sweep
        # base with a per-item ${.variable}); leave it unresolved for later.
        try:
            if cfg.save_dir is not None:
                with open_dict(cfg):
                    cfg.save_dir = str(cfg.save_dir)
        except Exception:
            pass
        return

    if cfg.save_dir is None:
        return

    base = str(cfg.save_dir)

    if policy == "timestamp":
        from datetime import datetime

        ts = datetime.now().strftime(config.TIMESTAMP_FORMAT)
        with open_dict(cfg):
            cfg.save_dir = str(Path(base) / ts)
        return

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
            return
        raise RuntimeError(
            f"apply_save_dir_policy: could not claim an incremented save_dir "
            f"under {base!r} after 1000 attempts."
        )

    from .exceptions import FlexLockValidationError

    raise FlexLockValidationError(
        f"Unknown save_dir_policy {policy!r}; expected None, 'increment', "
        f"or 'timestamp'."
    )
