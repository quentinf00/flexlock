- [x] in @naga/snapshot.py the commit_cwd does not work if there is an unstaged deleted source file, add a test and fix it
- Increase argument flexibility in @naga/runlock.py runlock function:
    - allow single string or array of strings for repos and data to directly give path to github repos or data to hash, the corresponding key(s) in the config should be:
        - the directory name for repos
        - the path of the data for data
        - add warning when overriding
- Register resolvers helpers for save_dir during naga import:
    - [x] "now" = lambda fmt: now().strftime(fmt)
    - [x] "vinc" = that takes a path as argument  get all folder/files that starts with this path in the directory, parses the integer at the end and return an increment and add an integer at the end depending of the maximum value already: see below get_next_versioned_path(path: str, fmt: str = '_{i:04d}') -> Path


```python
import re
from pathlib import Path

def get_next_versioned_path(path: str, fmt: str = '_{i:04d}') -> Path:
    """
    Finds the highest existing version of a folder/file and returns the next versioned path.

    Args:
        path: The base path for the folder/file (e.g., './my_folder').
        fmt: A format string for the version number. It must contain '{i}'.

    Returns:
        A Path object for the new versioned folder/file.
    """
    p = Path(path)
    parent_dir = p.parent
    base_name = p.name

    # Create a regex to extract the version number from the format string
    # This makes the parsing robust to different format strings.
    regex_pattern = re.escape(fmt).replace(r'\{i.*\}', r'(\d+)')
    regex = re.compile(f"^{re.escape(base_name)}{regex_pattern}")

    highest_version = -1
    if not parent_dir.exists():
        parent_dir.mkdir(parents=True)

    for item in parent_dir.glob(f"{base_name}*"):
        match = regex.match(item.name)
        if match:
            version = int(match.group(1))
            if version > highest_version:
                highest_version = version

    next_version = highest_version + 1
    version_str = fmt.format(i=next_version)
    
    return parent_dir / f"{base_name}{version_str}"
```

- [ ] Improve the logging behaviour: I want in each file to call log = logging.getLogger(__name__) and when I import naga, by default: the logs are printed to stdout with level debug when env variable NAGA_DEBUG=1.
    - in clicfg:
        - [ ]  a handler is added to log to a file (in the save_dir by default)
        - [ ]  add verbose parameter to set loglevel to debug
        - [ ]  add quiet parameter to not remove stdout handler
        - [ ]  add logfile parameter (default to save_dir / experiment.log)

- implement the docs/advanced features

## Big Refactor: Renaming and Rebranding

- [ ] **Rename Library (`naga` -> `flexlock`)**:
    - [ ] Change the main package directory name from `naga` to `flexlock`.
    - [ ] Update `pyproject.toml` and any other packaging files (`pixi.toml`, etc.) to reflect the new name `flexlock`.
    - [ ] Update all internal imports to use `from flexlock import ...`.

- [ ] **Rename Core Functions**:
    - [ ] Rename `clicfg` to `flexcli` in its definition and all call sites.
    - [ ] Rename `runlock` to `snapshot` in its definition and all call sites.
    - [ ] Rename `mlflow_lock` to `mlflowlink` in its definition and all call sites.
    - [ ] Rename `unsafe_debug` to `debug_on_fail` in its definition and all call sites.

- [ ] **Update File Names**:
    - [ ] Rename `naga/clicfg.py` to `flexlock/flexcli.py`.
    - [ ] Rename `naga/runlock.py` to `flexlock/snapshot.py`.
    - [ ] Rename `naga/mlflow_log.py` to `flexlock/mlflowlink.py`.
    - [ ] Rename `naga/debug.py` to `flexlock/debug_on_fail.py`.
    - [ ] Update corresponding test file names (e.g., `tests/test_runlock.py` -> `tests/test_snapshot.py`).

- [ ] **Update Documentation and User-Facing Strings**:
    - [ ] Search and replace all occurrences of "Naga", "clicfg", "runlock", etc., in the documentation (`.md` files).
    - [ ] Update any user-facing strings, such as help messages in `flexcli`.
    - [ ] Update the new `push_pull_workflow.md` to use the new terminology.

- [ ] **Review and Finalize**:
    - [ ] Perform a full project-wide search for any remaining instances of the old names.
    - [ ] Run all tests to ensure the refactoring is complete and correct.
    - [ ] Update the `README.md` to reflect the new branding.

## Push/Pull Workflow Implementation

- [ ] **`runlock` Function Enhancement**:
    - [ ] In the `repos` section of `run.lock`, also store the git remote URL along with the commit hash.

- [ ] **Core Persistence Logic (`naga/persist.py`)**:
    - [ ] Create `parse_runlock_tree(path)`: A function to recursively walk a `run.lock` and its `prevs` to aggregate all code (repos, commits, URLs) and data dependencies (absolute paths).
    - [ ] Create `get_git_remote_url(path)`: A helper to retrieve the remote URL of a local git repository.
    - [ ] Create `create_manifest(...)`: A function that takes the aggregated data from `parse_runlock_tree` and generates the manifest dictionary.
    - [ ] Create `push_artifacts(artifact_paths, remote_path)`: A function that calculates the content hash for each artifact and uses `rclone` to push it to a content-addressable store.
    - [ ] Create `pull_artifacts(manifest, target_dir, remote_path)`: A function that reads a manifest, recreates the original filesystem structure under a `fsroot/` directory, and uses `rclone link` to link to the data in the remote store.

- [ ] **Path Remapping Utility (`naga/path.py`)**:
    - [ ] Create `remap_paths(config, new_root)`: A function that walks through an OmegaConf object and prepends the `new_root` to every string that looks like an absolute path.

- [ ] **CLI Implementation (`naga/cli/main.py`)**:
    - [ ] Set up a CLI application (e.g., using `argparse` or `click`).
    - [ ] Implement the `naga push` command:
        - [ ] Takes `<path/to/run.lock>` and `--main-repo-path` as arguments.
        - [ ] Orchestrates the calls to `parse_runlock_tree`, `push_artifacts`, `create_manifest`.
        - [ ] Creates and pushes the final annotated git tag to the main repo's remote.
    - [ ] Implement the `naga pull` command:
        - [ ] Takes `<tag_name>` and `--target-dir` as arguments.
        - [ ] Fetches the tag, extracts and parses the manifest.
        - [ ] Clones all repos and checks out the correct commits.
        - [ ] Orchestrates the call to `pull_artifacts`.
        - [ ] Creates the convenience symlinks (`config.yaml`, `run.lock`).
        - [ ] Prints the final command required to reproduce the run.

