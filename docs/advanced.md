# Advanced Topics

This section covers advanced features of FlexLock that provide more power and flexibility for complex workflows.

## Resolvers

Resolvers allow you to dynamically fetch information and embed it directly into your configuration. This is particularly useful for making your `snapshot` definitions more declarative.

Instead of creating the `snapshot` imperatively in your Python script, you can specify the data and previous stage dependencies directly in your YAML configuration.

### Example

Consider a training stage that depends on a preprocessing stage.

**Configuration (`config.yml`):**

```yaml
# config.yml
training_data: '${snapshot:data/preprocessed/features.csv, training_data}'
```

**Python Script:**

```python
# train.py
from flexlock import flexcli, snapshot

class Config:
    training_data: str

@flexcli(config_class=Config)
def main(cfg: Config):
    # ... your training logic ...

    # The snapshot is now created from the resolved config
    snapshot(config=cfg, **cfg.snapshot)
```

When you run `python train.py --config config.yml`, FlexLock's `snapshot` resolvers will automatically:
1.  add an entry in the snapshot data section (computing the hash of the path)
2.  try adding an entry in the snapshot prev section and do so if a run.lock if found

The resolvers works like this:
```python
def snapshot_resolver(path, key=None):
    item = path if key is None else {key: path}
    snapshot(data=item, prevs=item, merge=True) # The merge keyword append to the run.lock 
    return path # return the actual path
```

This approach keeps your configuration self-contained and your Python script cleaner and more focused on logic.

Warning: When reproducing a run from the saved config `python script.py --config result/xp_XXX/run.lock --experiment config` the config file will have been resolved and therefore will not rerun the the snapshot resolvers
Use the save_config='unresolved' argument (default) in the snapshot function to save a 'config.yaml' file before resolution.
The command `python script.py --config result/xp_XXX/config.yaml` will then rerun the script and the resolver

## Persisting Runs (Push/Pull)

For ultimate reproducibility and collaboration, especially across different machines, you need a way to persist and retrieve the exact state of a run—both the code and the data. FlexLock proposes a workflow for "pushing" and "pulling" runs.

### The `push` Operation

A "push" script would perform the following actions for a given `run.lock`:
1.  **Code**:
    -   Gather all Git commits referenced in the `run.lock` and its predecessors.
    -   Create a clean branch containing this exact code state.
    -   Push this branch to a central Git repository and create a unique tag (e.g., based on the run's UUID).
2.  **Data**:
    -   Identify all data dependencies from the `run.lock` (both from the `data` section and from previous stages).
    -   Copy all these files and directories to a remote storage location (e.g., S3, an NFS share) using a tool like `rclone`.
    -   Organize the remote data under a path that matches the Git tag, ensuring a one-to-one correspondence between the code and data snapshots.

### The `pull` Operation

A "pull" script would perform the reverse:
1.  **Code**:
    -   Given a tag, check out the corresponding branch from the central Git repository.
2.  **Data**:
    -   Download the data snapshot from the remote storage that corresponds to that tag.
    -   Place the data in the expected local paths. (It could also create symlinks if the data is on a shared filesystem to save space).

This push/pull mechanism ensures that anyone can perfectly replicate the conditions of a run on any machine, making your research and production workflows robust and portable.
