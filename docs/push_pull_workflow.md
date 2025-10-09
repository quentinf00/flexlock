# FlexLock Push/Pull Workflow for Ultimate Reproducibility

This document outlines a robust, Git-centric workflow for persisting and retrieving the complete state of a FlexLock run. The goal is to ensure that any experiment can be perfectly replicated on any machine by anyone with access to the central code and data repositories.

## Core Concepts

1.  **The Git Tag is the Run**: The single source of truth for a persisted run is an **annotated git tag** in the main project repository. This tag is atomic and uniquely identifies a run.
2.  **The Manifest**: The tag's annotation message contains a `manifest.yaml`. This manifest is the key to reproducibility, containing all the metadata needed to pull and reconstruct the run's environment.
3.  **Content-Addressable Storage**: All data and run artifacts are stored in a remote location (e.g., S3, GCS, NFS) using a content-addressable scheme. This means objects are stored based on the hash of their content, providing automatic deduplication and ensuring data integrity.

---

## The `push` Workflow

The `flexlock push` command bundles the code, data, and run artifacts and uploads them to remote storage, creating an immutable, shareable snapshot of the run.

**Command:**
```bash
flexlock push <path/to/run.lock> --main-repo-path <path/to/main/repo>
```

**Sequence of Steps:**

1.  **Parse `run.lock` Tree**: The script recursively parses the specified `run.lock` and any predecessors in its `prevs` section to gather a complete list of:
    *   All Git repositories (local path, commit hash, and remote URL).
    *   All data dependencies (local absolute paths).

2.  **Identify Run Artifacts**: The primary `run.lock` and the corresponding `config.yaml` (unresolved) from the same directory are identified as key run artifacts.

3.  **Push Artifacts to Store**: For every data dependency and run artifact (including the `run.lock` and `config.yaml`):
    *   Its content hash (e.g., `xxh64`) is calculated.
    *   The artifact is copied to the content-addressable store using its hash as the key. `rclone` is ideal for this, as it naturally handles deduplication.
    ```bash
    # Example: Copy a dataset to the remote store
    rclone copy /path/to/dataset.csv flexlock-storage:store/xxh64-a1b2c3d4/
    ```

4.  **Generate Manifest**: A manifest is created in memory with all the gathered information.

5.  **Create and Push Atomic Git Tag**:
    *   A unique, descriptive tag name is generated (e.g., `flexlock/run/YYYYMMDD-HHMMSS-<short_hash>`).
    *   An annotated git tag is created in the main repository. The manifest is embedded directly into the tag's message.
    *   The tag is pushed to the remote (`git push origin <tag_name>`). This single, atomic action publishes the run.

**Example Manifest (in Git Tag Message):**
```yaml
# --- FlexLock Run Manifest ---
version: 1.1
repos:
  main_repo:
    url: git@github.com:user/my-repo.git
    commit: abc1234
  dep_repo:
    url: git@github.com:user/dep-repo.git
    commit: def5678
data:
  /home/user/data/dataset.csv: xxh64-a1b2c3d4
  /home/user/project/outputs/prev_run: xxh64-e5f6g7h8
artifacts:
  run_lock:
    original_path: /home/user/project/outputs/my_run/run.lock
    hash: xxh64-b4a3c2d1
  config_yaml:
    original_path: /home/user/project/outputs/my_run/config.yaml
    hash: xxh64-f8e7g6h5
```

---

## The `pull` Workflow

The `flexlock pull` command reconstructs the exact environment of a persisted run in a local directory.

**Command:**
```bash
flexlock pull <tag_name> --target-dir ./replicated-run
```

**Sequence of Steps:**

1.  **Fetch Tag and Parse Manifest**: The script fetches the specified git tag and extracts the manifest from its annotation message.

2.  **Pull Code**: Each repository listed in the manifest is cloned, and the exact commit is checked out into a `code/` subdirectory.

3.  **Recreate Filesystem**:
    *   A `fsroot/` directory is created to serve as the new root for all absolute paths.
    *   For every `data` and `artifacts` entry in the manifest, the original absolute path is recreated within `fsroot/`.
    *   `rclone link` is used to create a local file that points to the corresponding object in the remote content-addressable store. This is extremely efficient on shared filesystems.
    ```bash
    # Recreate a linked dataset
    rclone link flexlock-storage:store/xxh64-a1b2c3d4 ./replicated-run/fsroot/home/user/data/dataset.csv
    ```

4.  **Create Convenience Symlinks**: For ease of use, top-level symlinks are created in the target directory:
    *   `./replicated-run/config.yaml` -> `fsroot/path/to/original/config.yaml`
    *   `./replicated-run/run.lock` -> `fsroot/path/to/original/run.lock`

---

## How to Reproduce a Pulled Run

To make a script capable of running in a pulled environment, a small modification is required to handle path remapping.

1.  **Pull the run**: `flexlock pull <tag_name> --target-dir ./my-repro`
2.  **Modify the script for reproducibility**:

    ```python
    # In your main script (e.g., train.py)
    from flexlock import flexcli, snapshot
    from flexlock.path import remap_paths # A new, proposed utility
    import os

    @flexcli(...)
    def main(cfg):
        # If running in a pulled environment, remap all paths in the config
        if "FLEXLOCK_PULLED_RUN_ROOT" in os.environ:
            cfg = remap_paths(cfg, new_root=os.environ["FLEXLOCK_PULLED_RUN_ROOT"])

        # The rest of your script logic remains unchanged
        # ...
        snapshot(cfg, ...)
    ```

3.  **Execute the run**: The `pull` command will output the precise command needed to reproduce the run.

    ```bash
    # Set the environment variable to tell FlexLock where the new filesystem root is
    export FLEXLOCK_PULLED_RUN_ROOT=$(pwd)/my-repro/fsroot

    # Run the original script using the pulled, unresolved config
    python ./my-repro/code/main_repo/path/to/train.py --config ./my-repro/config.yaml
    ```
This ensures that the script re-runs the resolvers but operates on the remapped, correct paths, achieving perfect reproducibility.
