"""Pure, stable run fingerprints.

A *fingerprint* is a deterministic digest over the inputs that define a run:

  * the resolved config, with ``save_dir`` **prefix-normalized** so two runs
    that differ only in where they write share a fingerprint;
  * per-repo git **tree hashes** (via :func:`create_shadow_tree` — no commit,
    no ref side effects), restricted to each repo's ``include``/``exclude``
    pathspec so the "relevant files unchanged" notion becomes plain digest
    equality rather than a special case in the matcher;
  * data hashes for tracked data paths;
  * **environment** hashes: the content of dependency lockfiles
    (``pixi.lock``, ``uv.lock``, ...) found at each tracked repo's root, so a
    package upgrade is a cache miss. Absent when no lockfile is found or when
    ``FLEXLOCK_HASH_ENV=0``, which leaves the digest unchanged for such
    projects.

The digest is the single key used by the project-wide index (see ``index.py``)
to decide cache hits, so it must be stable across processes and machines for
identical inputs.
"""

import hashlib
import json
import os
from typing import Any, Mapping, Optional

from omegaconf import OmegaConf, DictConfig

from .git_utils import create_shadow_tree
from .data_hash import hash_data
from . import config as _config

# Placeholder substituted for the run's own save_dir so location doesn't leak
# into the fingerprint.
SAVE_DIR_PLACEHOLDER = "<SAVE_DIR>"

# Keys that describe *tracking intent* rather than run inputs; excluded from the
# config portion of the digest.
_TRACKING_KEYS = ("_snapshot_",)


def _to_container(cfg: Any) -> Any:
    """Resolve an OmegaConf config to a plain container; pass dicts through."""
    if isinstance(cfg, DictConfig):
        return OmegaConf.to_container(cfg, resolve=True)
    if OmegaConf.is_config(cfg):
        return OmegaConf.to_container(cfg, resolve=True)
    return cfg


def _normalize_paths(value: Any, save_dir: Optional[str]) -> Any:
    """Replace the run's save_dir *prefix* with a stable placeholder.

    Only an exact match or a genuine path prefix (``save_dir`` + separator) is
    rewritten — never an arbitrary substring — so unrelated paths that merely
    start with the same characters are left untouched.
    """
    if not save_dir:
        return value
    if isinstance(value, str):
        if value == save_dir:
            return SAVE_DIR_PLACEHOLDER
        if value.startswith(save_dir + os.sep):
            return SAVE_DIR_PLACEHOLDER + value[len(save_dir):]
        return value
    if isinstance(value, dict):
        return {k: _normalize_paths(v, save_dir) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_paths(v, save_dir) for v in value]
    return value


def canonical_config(cfg: Any) -> Any:
    """Return the config portion of the fingerprint: resolved, save_dir-
    normalized, and stripped of tracking-only keys."""
    container = _to_container(cfg)
    if not isinstance(container, dict):
        return container

    save_dir = container.get("save_dir")
    # Drop the run's own save_dir and tracking keys, then normalize any nested
    # references to save_dir into the placeholder.
    stripped = {
        k: v
        for k, v in container.items()
        if k != "save_dir" and k not in _TRACKING_KEYS
    }
    return _normalize_paths(stripped, save_dir if isinstance(save_dir, str) else None)


def _repo_tree(repo_info: Mapping[str, Any]) -> str:
    """Tree hash for one tracked repo, restricted to its include/exclude."""
    result = create_shadow_tree(
        repo_info["path"],
        include=repo_info.get("include"),
        exclude=repo_info.get("exclude"),
    )
    return result["tree"]


_lockfile_cache: dict = {}


def _file_digest(path: str) -> str:
    """sha256 of a file, memoized on (path, mtime, size) for the process."""
    st = os.stat(path)
    key = (path, st.st_mtime_ns, st.st_size)
    digest = _lockfile_cache.get(key)
    if digest is None:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        digest = h.hexdigest()
        _lockfile_cache[key] = digest
    return digest


def _repo_root(path: str) -> Optional[str]:
    from git.repo import Repo as GitRepo

    try:
        return GitRepo(path, search_parent_directories=True).working_tree_dir
    except Exception:
        return None


def env_hashes(repos: Optional[Mapping[str, Mapping[str, Any]]]) -> dict:
    """Hash dependency lockfiles at the root of each tracked repo.

    Returns ``{"<repo>/<lockfile>": sha256}``; empty when hashing is disabled
    or no lockfile exists. Keys use the repo *name*, not its absolute path, so
    the digest is stable across machines that mount the repo elsewhere.
    """
    if not repos or not _config.hash_env_enabled():
        return {}
    names = _config.env_lockfile_names()
    out = {}
    for repo_name, info in sorted(repos.items()):
        root = _repo_root(info["path"])
        if root is None:
            continue
        for lock_name in names:
            lock_path = os.path.join(root, lock_name)
            if os.path.isfile(lock_path):
                out[f"{repo_name}/{lock_name}"] = _file_digest(lock_path)
    return out


def fingerprint(
    cfg: Any,
    repos: Optional[Mapping[str, Mapping[str, Any]]] = None,
    data: Optional[Mapping[str, str]] = None,
    use_cache: bool = True,
) -> str:
    """Compute the stable fingerprint digest for a run.

    Args:
        cfg: The run config (OmegaConf or plain dict). Resolved and
            save_dir-normalized before hashing.
        repos: ``{name: {path, include?, exclude?, module?}}`` — per-repo git
            identity. Tree hashes are computed via ``create_shadow_tree``.
        data: ``{name: path}`` data inputs to hash.
        use_cache: Passed through to :func:`hash_data` for data paths.

    Returns:
        A hex sha256 digest.
    """
    parts: dict[str, Any] = {"config": canonical_config(cfg)}

    if repos:
        parts["repos"] = {
            name: _repo_tree(info) for name, info in sorted(repos.items())
        }

    env = env_hashes(repos)
    if env:
        parts["env"] = env

    if data:
        parts["data"] = {
            name: hash_data(path, use_cache=use_cache)
            for name, path in sorted(data.items())
        }

    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
