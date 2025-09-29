"""Utility for creating and managing the `run.lock` file."""
import os
import tempfile
import yaml
import inspect
from pathlib import Path
from omegaconf import OmegaConf, DictConfig
from git import Repo

from .data_hash import hash_data
from .load_stage import load_stage_from_path
from .snapshot import commit_cwd, get_git_commit

def _get_caller_info(repos: dict) -> dict:
    """Gets information about the function that called runlock."""
    try:
        caller_frame = inspect.stack()[2] # Go back 2 frames to get the actual caller
        caller_module = inspect.getmodule(caller_frame[0])
        
        caller_info = {
            "module": caller_module.__name__ if caller_module else Path(caller_frame.filename).name,
            "function": caller_frame.function,
            "filepath": caller_module.__file__ if caller_module else caller_frame.filename,
            "repo": None,
        }

        # Find which repo the caller file belongs to
        if repos:
            abs_caller_path = Path(caller_frame.filename).resolve()
            for repo_name, repo_path in repos.items():
                repo = Repo(repo_path, search_parent_directories=True)
                repo_root = Path(repo.working_dir).resolve()
                if abs_caller_path.is_relative_to(repo_root):
                    caller_info["filepath"] = str(abs_caller_path.relative_to(repo_root))
                    caller_info["repo"] = repo_name
                    break # Stop after finding the first matching repo
        
        return caller_info

    except IndexError:
        return {"module": "unknown", "function": "unknown"}

def _get_repo_info(
    repos: dict,
    commit: bool,
    commit_branch: str,
    commit_message: str,
) -> dict:
    """
    Gets the commit hash for each repo, creating a new commit if requested.
    """
    if repos is None:
        return {}
    
    commit_hashes = {}
    for name, path in repos.items():
        if commit:
            new_commit = commit_cwd(
                branch=commit_branch,
                message=commit_message,
                repo_path=path
            )
            commit_hashes[name] = new_commit.hexsha
        else:
            commit_hashes[name] = get_git_commit(path)
    return commit_hashes

def _atomic_write_yaml(data: dict, path: Path):
    """Writes a dictionary to a YAML file atomically."""
    temp_fd, temp_path_str = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp-")
    temp_path = Path(temp_path_str)
    with os.fdopen(temp_fd, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    os.rename(temp_path, path)

def runlock(
    config: DictConfig,
    repos: dict = None,
    data: dict = None,
    prevs: list = None,
    runlock_path: str = None,
    merge: bool = False,
    commit: bool = True,
    commit_branch: str = "naga-run-logs",
    commit_message: str = "Naga: Auto-snapshot",
    mlflow_log: bool = True,
):
    """
    Writes a `run.lock` file with the state of the experiment.

    Args:
        config (DictConfig): The OmegaConf configuration object for the run.
        repos (dict, optional): A dictionary mapping a name to a git repository path 
                                (e.g., {'main_repo': '.'}).
        data (dict, optional): A dictionary mapping a name to a data path to be hashed
                               (e.g., {'raw_data': 'path/to/data'}).
        prevs (list, optional): A list of paths to previous stage directories to be included.
        runlock_path (str, optional): The explicit path to the `run.lock` file. 
                                      If None, defaults to `config.save_dir / 'run.lock'`.
        merge (bool, optional): If True and a `run.lock` file already exists, it will be
                                read, updated with the new information, and written back.
        commit (bool, optional): If True, create a new commit to capture the state of each repo.
                                 If False, record the current commit hash. Defaults to True.
        commit_branch (str, optional): The branch to commit to if `commit=True`.
        commit_message (str, optional): The commit message to use if `commit=True`.
    """
    if runlock_path:
        lock_file = Path(runlock_path)
    elif "save_dir" in config:
        lock_file = Path(config.save_dir) / "run.lock"
    else:
        raise ValueError("Either `runlock_path` must be provided or `config` must have a `save_dir` key.")

    lock_file.parent.mkdir(parents=True, exist_ok=True)

    run_data = {}
    if merge and lock_file.exists():
        with open(lock_file, 'r') as f:
            run_data = yaml.safe_load(f) or {}

    # --- Capture Caller and Repo Info First ---
    run_data["caller"] = _get_caller_info(repos)
    
    if repos:
        repo_info = _get_repo_info(repos, commit, commit_branch, commit_message)
        run_data.setdefault("repos", {}).update(repo_info)

    # --- Update with other information ---
    run_data["config"] = OmegaConf.to_container(config, resolve=True)
    
    if data:
        data_hashes = {name: hash_data(path) for name, path in data.items()}
        run_data.setdefault("data", {}).update(data_hashes)

    if prevs:
        previous_stages_data = {}
        for path in prevs:
            previous_stages_data.update(load_stage_from_path(path))
        run_data.setdefault("prevs", {}).update(previous_stages_data)

    # Write the file atomically
    _atomic_write_yaml(run_data, lock_file)
    if mlflow_log:
        from .mlflow_log import mlflow_lock
        with mlflow_lock(str(lock_file.parent)) as _:
            pass
