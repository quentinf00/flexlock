"""Source code versioning utilities for FlexLock."""

import fnmatch
import os
import shutil
import uuid
import warnings
from pathlib import Path
from contextlib import contextmanager
from git.repo import Repo as GitRepo

from .exceptions import FlexLockSnapshotError


@contextmanager
def shadow_index(repo: GitRepo):
    """Context manager for Git Plumbing operations without touching user index."""
    git_dir = Path(repo.git_dir)
    temp_index = git_dir / f"index_shadow_{uuid.uuid4().hex}"

    # Clone current index to temp file for speed
    try:
        if (git_dir / "index").exists():
            shutil.copy2(git_dir / "index", temp_index)
    except Exception:
        pass

    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(temp_index)

    try:
        yield env
    finally:
        if temp_index.exists():
            temp_index.unlink()


def sanitize_ref_name(name: str) -> str:
    """Sanitize a string to be a valid git ref name."""
    invalid_chars = [" ", "~", "^", ":", "?", "*", "[", "\\", "..", "@{", "//"]
    for char in invalid_chars:
        name = name.replace(char, "_")
    return name


def create_shadow_snapshot(
    repo_path: str = ".",
    ignore_patterns: list | None = None,
    ref_name: str | None = None,
) -> dict:
    """
    Creates a Shadow Commit.
    Returns: {commit_hash, tree_hash, is_dirty}
    """
    repo = GitRepo(repo_path, search_parent_directories=True)
    ignore_patterns = ignore_patterns or []

    with shadow_index(repo) as shadow_env:
        git = repo.git

        # 1. Stage everything (Modified + Untracked) into Shadow Index
        git.add("--all", env=shadow_env)

        # 2. Remove ignored patterns from Shadow Index
        if ignore_patterns:
            try:
                git.rm(
                    "--cached",
                    "-r",
                    "--ignore-unmatch",
                    *ignore_patterns,
                    env=shadow_env,
                )
            except Exception:
                pass

        # 3. Write Tree (This is the content fingerprint)
        tree_hash = git.write_tree(env=shadow_env)

        # 4. Create Shadow Commit (Lineage)
        parent = repo.head.commit.hexsha
        msg = f"FlexLock Shadow: {parent[:7]} + Changes"
        shadow_commit = git.commit_tree(
            tree_hash, "-p", parent, "-m", msg, env=shadow_env
        )

        # 5. Save Ref (Prevent Garbage Collection)
        ref_name = f"refs/flexlock/runs/{ref_name or shadow_commit}"
        git.update_ref(sanitize_ref_name(ref_name), shadow_commit)

        return {
            "commit": shadow_commit,
            "tree": tree_hash,  # <--- The key for Equality Checks
            "is_dirty": repo.is_dirty(untracked_files=True),
        }


def create_shadow_tree(
    repo_path: str = ".",
    include: list | None = None,
    exclude: list | None = None,
) -> dict:
    """Compute a content tree hash for a working tree without side effects.

    Unlike :func:`create_shadow_snapshot`, this stages into a throwaway shadow
    index and runs **``write-tree`` only** — it creates no commit object and no
    ``refs/flexlock/runs/*`` ref. It is therefore safe to call on every
    fingerprint check (smart-run) without accumulating objects/refs in ``.git``.

    Args:
        repo_path: Path inside the repository.
        include: Optional pathspec(s); when given, only these paths are staged
            (the fingerprint is restricted to the "relevant" subtree, so an
            include-match becomes plain tree-hash equality). Defaults to all
            tracked + untracked files.
        exclude: Optional pathspec(s) removed from the staged index.

    Returns:
        dict: ``{"tree": <hash>, "is_dirty": <bool>}``.
    """
    repo = GitRepo(repo_path, search_parent_directories=True)
    include = include or None
    exclude = exclude or []

    with shadow_index(repo) as shadow_env:
        git = repo.git

        # 1. Stage into the shadow index. Restrict to `include` when provided so
        #    the tree hash only reflects the relevant subtree.
        if include:
            git.add("--", *include, env=shadow_env)
        else:
            git.add("--all", env=shadow_env)

        # 2. Drop excluded patterns from the shadow index.
        if exclude:
            try:
                git.rm(
                    "--cached", "-r", "--ignore-unmatch", *exclude, env=shadow_env
                )
            except Exception:
                pass

        # 3. Write the tree — the content fingerprint. No commit, no ref.
        tree_hash = git.write_tree(env=shadow_env)

        return {
            "tree": tree_hash,
            "is_dirty": repo.is_dirty(untracked_files=True),
        }


def get_git_tree_hash(path: str = ".") -> str:
    """
    Gets the current git tree hash for a repository without creating a new commit.
    This represents the content fingerprint of the repository.

    Args:
        path (str): The path to the git repository.

    Returns:
        str: The tree hash.

    Raises:
        FlexLockSnapshotError: if ``path`` is not a usable git repository.
    """
    try:
        repo = GitRepo(path, search_parent_directories=True)
        # Get the tree hash of the current commit
        return repo.head.commit.tree.hexsha
    except Exception as e:
        raise FlexLockSnapshotError(
            f"Could not get git tree hash for {path!r}: {e}"
        ) from e


def get_git_commit(path: str = ".") -> str:
    """
    Gets the current commit hash for a git repository without creating a new commit.

    Args:
        path (str): The path to the git repository.

    Returns:
        str: The commit hash.

    Raises:
        FlexLockSnapshotError: if ``path`` is not a usable git repository.
    """
    try:
        repo = GitRepo(path, search_parent_directories=True)
        return repo.head.commit.hexsha
    except Exception as e:
        raise FlexLockSnapshotError(
            f"Could not get git commit for {path!r}: {e}"
        ) from e


_tree_listing_cache: dict = {}


def _tree_blobs(repo: GitRepo, tree: str) -> dict:
    """``{repo-relative path: blob sha}`` for every file in ``tree`` (memoized)."""
    key = (repo.working_tree_dir, tree)
    listing = _tree_listing_cache.get(key)
    if listing is None:
        listing = {}
        for line in repo.git.ls_tree("-r", "--full-tree", tree).splitlines():
            meta, path = line.split("\t", 1)
            listing[path] = meta.split()[2]
        _tree_listing_cache[key] = listing
    return listing


def _blob_sha(path: Path) -> str:
    """Git blob hash of a file (same as ``git hash-object``), without a subprocess."""
    import hashlib

    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def code_drift(repos: dict, since: float, modules=None) -> dict:
    """Loaded source files that differ from the recorded tree.

    A run records its code as a git tree at snapshot time, but Python loads a
    module when it is first imported: an edit made while the job waited in the
    queue, or before a lazy import, runs code the tree does not describe. This
    checks every module in ``modules`` (default ``sys.modules``) whose file lies
    in a recorded repo and was modified after ``since`` (epoch seconds of the
    snapshot); a file counts as drifted when its content differs from the
    tree's blob, or when it is a new, non-ignored file absent from the tree.

    Args:
        repos: The ``repos`` section of a run record
            (``{name: {"path": ..., "tree": ...}}``).
        since: Snapshot time; files with an older mtime are skipped unread.
        modules: Iterable of module objects (defaults to ``sys.modules``).

    Returns:
        ``{repo name: [repo-relative paths]}`` for repos with drift; empty
        when the loaded code matches the recorded tree.
    """
    import sys

    if modules is None:
        modules = list(sys.modules.values())
    files = set()
    for mod in modules:
        f = getattr(mod, "__file__", None)
        if f and f.endswith(".py"):
            try:
                files.add(Path(f).resolve())
            except OSError:
                continue

    drift = {}
    for name, info in (repos or {}).items():
        tree = info.get("tree") if isinstance(info, dict) else None
        if not tree or not info.get("path"):
            continue
        try:
            repo = GitRepo(info["path"], search_parent_directories=True)
            root = Path(repo.working_tree_dir).resolve()
            blobs = _tree_blobs(repo, tree)
        except Exception:
            continue

        changed, new = [], []
        for f in files:
            try:
                rel = f.relative_to(root).as_posix()
                if f.stat().st_mtime <= since:
                    continue
            except (ValueError, OSError):
                continue
            if rel in blobs:
                if _blob_sha(f) != blobs[rel]:
                    changed.append(rel)
            else:
                new.append(rel)

        if new:
            # New files only count if git would have tracked them (drops .pixi,
            # build dirs, ...). check-ignore exits 1 when nothing is ignored.
            try:
                ignored = set(repo.git.check_ignore(*new).splitlines())
            except Exception:
                ignored = set()
            changed.extend(p for p in new if p not in ignored)

        if changed:
            drift[name] = sorted(changed)
    return drift
