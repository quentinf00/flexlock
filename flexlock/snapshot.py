"""Utility for creating and managing the `run.lock` file."""

import os
import tempfile
import yaml
import inspect
from pathlib import Path
from omegaconf import OmegaConf, DictConfig

from .data_hash import hash_data
from .load_stage import load_stage_from_path
from .utils import to_dictconfig
from loguru import logger


def _get_caller_info(repos: dict) -> dict:
    """Gets information about the function that called snapshot."""
    try:
        from git import Repo

        caller_frame = inspect.stack()[2]  # Go back 2 frames to get the actual caller
        caller_module = inspect.getmodule(caller_frame[0])

        caller_info = {
            "module": caller_module.__name__
            if caller_module
            else Path(caller_frame.filename).name,
            "function": caller_frame.function,
            "filepath": caller_module.__file__
            if caller_module
            else caller_frame.filename,
            "repo": None,
        }

        # Find which repo the caller file belongs to
        if repos:
            abs_caller_path = Path(caller_frame.filename).resolve()
            for repo_name, repo_path in repos.items():
                repo = Repo(repo_path, search_parent_directories=True)
                repo_root = Path(repo.working_dir).resolve()
                if abs_caller_path.is_relative_to(repo_root):
                    caller_info["filepath"] = str(
                        abs_caller_path.relative_to(repo_root)
                    )
                    caller_info["repo"] = repo_name
                    break  # Stop after finding the first matching repo

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

    from .git_utils import commit_cwd, get_git_commit

    if repos is None:
        return {}

    commit_hashes = {}
    for name, path in repos.items():
        if commit:
            new_commit = commit_cwd(
                branch=commit_branch, message=commit_message, repo_path=path
            )
            commit_hashes[name] = new_commit.hexsha
        else:
            commit_hashes[name] = get_git_commit(path)
    return commit_hashes


def _atomic_write_yaml(data: dict, path: Path):
    """Writes a dictionary to a YAML file atomically."""
    temp_fd, temp_path_str = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.tmp-"
    )
    temp_path = Path(temp_path_str)
    with os.fdopen(temp_fd, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    os.rename(temp_path, path)


def snapshot(
    config: DictConfig,
    repos: dict | list | str | None = None,
    data: dict | list | str | None = None,
    prevs: list | str | None = None,
    snapshot_path: str | None = None,
    merge: bool = False,
    commit: bool = True,
    commit_branch: str = "flexlock-run-logs",
    commit_message: str | None = None,
    mlflowlink: bool = False,
    resolve: bool = True,
    prevs_from_data: bool = True,
    force: bool = False,
):
    """
    Writes a `run.lock` file with the state of the experiment.

    Args:
        config (DictConfig): The OmegaConf configuration object for the run.
        repos (dict, str, or list[str], optional):
            - A dictionary mapping a name to a git repository path (e.g., {'main_repo': '.'}).
            - A single path to a git repository. The key will be the directory name.
            - A list of paths to git repositories.
        data (dict, str, or list[str], optional):
            - A dictionary mapping a name to a data path to be hashed (e.g., {'raw_data': 'path/to/data'}).
            - A single path to a data file/directory. The key will be the full path.
            - A list of paths to data files/directories.
        prevs (list, optional): A list of paths to previous stage directories to be included.
        snapshot_path (str, optional): The explicit path to the `run.lock` file.
                                      If None, defaults to `config.save_dir / 'run.lock'`.
        merge (bool, optional): If True and a `run.lock` file already exists, it will be
                                read, updated with the new information, and written back.
        commit (bool, optional): If True, create a new commit to capture the state of each repo.
                                 If False, record the current commit hash. Defaults to True.
        commit_branch (str, optional): The branch to commit to if `commit=True`.
        commit_message (str, optional): The commit message to use if `commit=True`.
        mlflowlink (bool, optional): If True, logs the snapshot to MLflow. Defaults to False.
        resolve (bool, optional): Whether to resolve the OmegaConf config before snapshotting. Defaults to True.
        prevs_from_data (bool, optional): If True, automatically adds paths from the `data` argument to `prevs`. Defaults to True.
        force (bool, optional): If True, forces the creation of a new snapshot even if `run.lock` exists. Defaults to False.
    """

    with logger.catch(reraise=False):
        config = to_dictconfig(config)
        if snapshot_path:
            lock_file = Path(snapshot_path)
        elif "save_dir" in config:
            lock_file = Path(config.save_dir) / "run.lock"
        else:
            raise ValueError(
                "Either `snapshot_path` must be provided or `config` must have a `save_dir` key."
            )
        if lock_file.exists() and (merge or force):
            logger.info(
                f"File '{lock_file}' exists exiting (set force or merge to True to force execution or append to existing)."
            )
            return

        lock_file.parent.mkdir(parents=True, exist_ok=True)

        if resolve:
            OmegaConf.resolve(config)

        run_data = {}
        if merge and lock_file.exists():
            with open(lock_file, "r") as f:
                run_data = yaml.safe_load(f) or {}

        # --- Process flexible 'repos' and 'data' arguments ---
        def _process_arg(arg, is_repo=False):
            if not arg:
                return {}
            if isinstance(arg, str):
                arg = [arg]
            if isinstance(arg, list):
                new_dict = {}
                for path_str in arg:
                    path = Path(path_str)
                    key = path.absolute().name
                    if key in new_dict:
                        logger.error(
                            f"Key '{key}' is being overridden in {'repos' if is_repo else 'data'} use dict syntax to specify unique key for arg."
                        )
                        raise Exception(
                            f"Runlock key collision {'repos' if is_repo else 'data'}"
                        )
                    new_dict[key] = str(path)
                return new_dict
            return arg

        repos = _process_arg(repos, is_repo=True)
        data = _process_arg(data)

        # --- Capture Caller and Repo Info First ---
        run_data["caller"] = _get_caller_info(repos)

        if repos:
            if commit_message is None:
                commit_message = f"Snapshot {OmegaConf.select(config, 'save_dir')}"
            repo_info = _get_repo_info(repos, commit, commit_branch, commit_message)
            run_data.setdefault("repos", {}).update(repo_info)

        # --- Update with other information ---
        run_data["config"] = OmegaConf.to_container(config, resolve=True)

        if data:
            data_hashes = {name: hash_data(path) for name, path in data.items()}
            run_data.setdefault("data", {}).update(data_hashes)

        if prevs:
            if isinstance(prevs, str):
                prevs = [prevs]
        if prevs_from_data:
            if prevs:
                prevs = prevs + list(data.values())
            else:
                prevs = list(data.values())

        if prevs:

            def _find_snapshot_dir(start_path: Path) -> Path | None:
                """Search for `run.lock` in `start_path` and its parents."""
                p = start_path.resolve()
                if p.is_file():
                    p = p.parent

                while p != p.parent:  # Stop at the root directory
                    if (p / "run.lock").exists():
                        return p
                    p = p.parent
                return None

            previous_stages_data = {}
            for path_str in prevs:
                snapshot_dir = _find_snapshot_dir(Path(path_str))
                if snapshot_dir:
                    stage_data = load_stage_from_path(str(snapshot_dir))
                    # The key from load_stage_from_path is the full path,
                    # we want to use the directory name as the key.
                    original_key = next(iter(stage_data))
                    previous_stages_data[snapshot_dir.name] = stage_data[original_key]
                else:
                    logger.warning(
                        f"Could not find a 'run.lock' file for the previous stage at or above '{path_str}'."
                    )

            run_data.setdefault("prevs", {}).update(previous_stages_data)

        # Write the file atomically
        _atomic_write_yaml(run_data, lock_file)

    # Dump any pending tasks from database to the YAML file (in case tasks were added before snapshot creation)
    if mlflowlink:
        from .mlflowlink import mlflowlink

        with mlflowlink(str(lock_file.parent)) as _:
            pass
        pass
