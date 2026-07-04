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
