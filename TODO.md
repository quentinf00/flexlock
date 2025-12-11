## Improvements 
### CLI interface
# FlexLock CLI Refactoring Plan

## 1. Interface & Arguments Renaming
- [ ] **Rename Selection Argument**
    - Change `-e, --experiment` to **`-s, --select`**.
    - Description: "Dot-separated key to select a sub-node from the base configuration."
- [ ] **Implement Two-Stage File Merging**
    - Rename/Add **`-m, --merge`**: Path to YAML file merged into the **Outer/Root** config (before selection).
    - Rename/Add **`-M, --merge-after-select`**: Path to YAML file merged into the **Inner/Selected** config (after selection).
- [ ] **Implement Two-Stage Dotlist Overrides**
    - Rename/Add **`-o, --overrides`**: Dot-list args applied to the **Outer/Root** config (before selection).
    - Rename/Add **`-O, --overrides-after-select`**: Dot-list args applied to the **Inner/Selected** config (after selection).

## 2. Configuration Loading Pipeline (Logic Refactor)
- [ ] **Step 1: Base Loading**
    - Load base config from `-c, --config`.
    - If no config file is provided, start with an empty `OmegaConf` object.
- [ ] **Step 2: Outer Overrides (Pre-Selection)**
    - Apply files from `-m / --merge`.
    - Apply dot-list from `-o / --overrides`.
    - *Result*: `outer_cfg` (Used for interpolation resolution and task lookup).
- [ ] **Step 3: Task Extraction**
    - If `--tasks-key` is provided, look it up inside `outer_cfg`.
    - If `--tasks` (file) is provided, load it.
    - Consolidate into a list of task config objects.
- [ ] **Step 4: Selection**
    - If `-s / --select` is present, extract the sub-node from `outer_cfg`.
    - If not present, `inner_cfg = outer_cfg`.
- [ ] **Step 5: Inner Overrides (Post-Selection)**
    - Apply files from `-M / --merge-after-select` to `inner_cfg`.
    - Apply dot-list from `-O / --overrides-after-select` to `inner_cfg`.
- [ ] **Step 6: Schema Application**
    - If `default_config` (dataclass) was provided to the decorator:
        - Convert `default_config` to DictConfig.
        - Merge `inner_cfg` *into* this default schema to ensure defaults are preserved and types are correct.
    - *Result*: `final_cfg` (The template used for execution).


## 4. Housekeeping & Validation
- [ ] **Conflict Checks**
    - Ensure `ipykernel` / `pytest` detection still works for determining CLI vs Programmatic mode.
    - Ensure `save_dir` resolution happens on the `final_cfg` (after all merges/selections).
- [ ] **Help Message**
    - Group arguments in `argparse` help (e.g., "Configuration Selection", "Global Overrides", "Local Overrides") to make the difference between `-o` and `-O` clear to the user.

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

