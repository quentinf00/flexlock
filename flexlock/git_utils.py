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


def create_shadow_snapshot(repo_path: str = ".", ignore_patterns: list | None = None):
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
                git.rm("--cached", "-r", "--ignore-unmatch", *ignore_patterns, env=shadow_env)
            except Exception:
                pass

        # 3. Write Tree (This is the content fingerprint)
        tree_hash = git.write_tree(env=shadow_env)

        # 4. Create Shadow Commit (Lineage)
        parent = repo.head.commit.hexsha
        msg = f"FlexLock Shadow: {parent[:7]} + Changes"
        shadow_commit = git.commit_tree(tree_hash, "-p", parent, "-m", msg, env=shadow_env)

        # 5. Save Ref (Prevent Garbage Collection)
        ref_name = f"refs/flexlock/runs/{shadow_commit}"
        git.update_ref(ref_name, shadow_commit)

        return {
            "commit": shadow_commit,
            "tree": tree_hash, # <--- The key for Equality Checks
            "is_dirty": repo.is_dirty(untracked_files=True)
        }


def commit_cwd(
    branch: str,
    message: str,
    repo_path: str = ".",
    include: list | None = None,
    exclude: list | None = None,
    filesize_warn: int = 1 * 1024 * 1024,  # 1MB
):
    """
    Finds all changed/untracked files in a git repository, filters them,
    and commits them to a specified branch.

    Args:
        branch (str): The branch to commit to. Will be created if it doesn't exist.
        message (str): The commit message.
        repo_path (str): Path to the git repository.
        include (list[str], optional): List of glob patterns to include.
        exclude (list[str], optional): List of glob patterns to exclude.
        filesize_warn (int, optional): Warn if a file to be committed is larger than this size in bytes.

    Returns:
        The git.Commit object of the new commit.
    """
    repo = GitRepo(repo_path, search_parent_directories=True)

    untracked_files = set(repo.untracked_files)
    modified_files = {item.a_path for item in repo.index.diff(None)}
    files_to_consider = untracked_files | modified_files

    if include:
        included_files = set()
        for pattern in include:
            included_files.update(fnmatch.filter(files_to_consider, pattern))
        files_to_consider = included_files

    if exclude:
        excluded_files = set()
        for pattern in exclude:
            excluded_files.update(fnmatch.filter(files_to_consider, pattern))
        files_to_consider -= excluded_files

    if not files_to_consider:
        return repo.head.commit

    # Check file sizes before adding
    for file_path in files_to_consider:
        full_path = os.path.join(repo.working_dir, file_path)
        if os.path.exists(full_path) and os.path.getsize(full_path) > filesize_warn:
            warnings.warn(
                f"File '{file_path}' is larger than {filesize_warn / 1024 / 1024:.2f} MB. "
                "Consider adding it to .gitignore or a flexlock-specific exclude file.",
                UserWarning,
            )

    index = repo.index

    # Separate files into 'to_add' and 'to_remove'
    files_to_add = [
        f
        for f in files_to_consider
        if os.path.exists(os.path.join(repo.working_dir, f))
    ]
    files_to_remove = [
        f
        for f in files_to_consider
        if not os.path.exists(os.path.join(repo.working_dir, f))
    ]

    if files_to_add:
        index.add(files_to_add)
    if files_to_remove:
        index.remove(files_to_remove)

    log_branch = getattr(repo.heads, branch, None) or repo.create_head(branch)
    parent_commit = log_branch.commit if log_branch.commit else repo.head.commit

    commit = index.commit(message, parent_commits=[parent_commit], head=False)
    log_branch.commit = commit
    return commit


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
