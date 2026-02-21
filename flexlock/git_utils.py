"""Source code versioning utilities for FlexLock."""

import fnmatch
import os
import shutil
import uuid
import warnings
from pathlib import Path
from contextlib import contextmanager
from git.repo import Repo as GitRepo


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


def get_git_tree_hash(path: str = ".") -> str:
    """
    Gets the current git tree hash for a repository without creating a new commit.
    This represents the content fingerprint of the repository.

    Args:
        path (str): The path to the git repository.

    Returns:
        str: The tree hash, or an error message if it fails.
    """
    try:
        repo = GitRepo(path, search_parent_directories=True)
        # Get the tree hash of the current commit
        return repo.head.commit.tree.hexsha
    except Exception as e:
        return f"Error getting git tree hash: {e}"


def get_git_commit(path: str = ".") -> str:
    """
    Gets the current commit hash for a git repository without creating a new commit.

    Args:
        path (str): The path to the git repository.

    Returns:
        str: The commit hash, or an error message if it fails.
    """
    try:
        repo = GitRepo(path, search_parent_directories=True)
        return repo.head.commit.hexsha
    except Exception as e:
        return f"Error getting git commit: {e}"
