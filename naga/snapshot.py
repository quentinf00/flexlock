"""Source code versioning decorator for Naga."""
import fnmatch
from functools import wraps

from git.repo import Repo as GitRepo
from .context import run_context

def commit_cwd(branch, message, repo_path=".", include=None, exclude=None):
    """
    Finds all changed/untracked files in the current git repository, filters them,
    and commits them to a specified branch.

    Args:
        branch (str): The branch to commit to. Will be created if it doesn't exist.
        message (str): The commit message.
        repo_path (str): Path to the git repository.
        include (list[str]): List of glob patterns to include. If None, all files are included.
        exclude (list[str]): List of glob patterns to exclude.
    """
    repo = GitRepo(repo_path, search_parent_directories=True)
    index = repo.index

    # 1. Get all relevant files (untracked and modified)
    untracked_files = set(repo.untracked_files)
    modified_files = {item.a_path for item in repo.index.diff(None)}
    files_to_consider = untracked_files | modified_files

    # 2. Apply include/exclude filters
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
        return repo.head.commit  # No changes to commit

    # 3. Add and commit
    index.add([str(f) for f in files_to_consider])

    # Get or create the target branch
    log_branch = getattr(repo.heads, branch, None) or repo.create_head(branch)
    
    # Determine parent commit
    parent_commit = log_branch.commit if log_branch.commit else repo.head.commit

    commit = index.commit(message, parent_commits=[parent_commit], head=False)
    log_branch.commit = commit
    return commit

def snapshot(branch="run_logs", message="Naga: Auto-snapshot", include=None, exclude=None, git_repo_path="."):
    """
    A decorator that automatically versions the source code of a project
    by taking a Git snapshot before running a function.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            commit = commit_cwd(branch, message, include=include, exclude=exclude, repo_path=git_repo_path)
            run_context.get()["git_commit"] = commit.hexsha
            return fn(*args, **kwargs)
        return wrapped
    return decorator
