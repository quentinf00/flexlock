
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

