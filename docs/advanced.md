# Advanced Topics

This section covers advanced features of Naga that provide more power and flexibility for complex workflows.

## Resolvers

Resolvers allow you to dynamically fetch information and embed it directly into your configuration. This is particularly useful for making your `runlock` definitions more declarative.

Instead of creating the `runlock` imperatively in your Python script, you can specify the data and previous stage dependencies directly in your YAML configuration.

### Example

Consider a training stage that depends on a preprocessing stage.

**Configuration (`config.yml`):**

```yaml
# config.yml
training_data: 'data/preprocessed/features.csv'

runlock:
  data:
    # Use the runlock_data resolver to hash the training data
    training_features: '${runlock_data:${training_data}}'
  prevs:
    # Use the runlock_prev resolver to link to the preprocessing stage
    preprocessing: '${runlock_prev:${training_data}}' 
```

**Python Script:**

```python
# train.py
from naga import clicfg, runlock

class Config:
    training_data: str
    runlock: dict

@clicfg(config_class=Config)
def main(cfg: Config):
    # ... your training logic ...

    # The runlock is now created from the resolved config
    runlock(config=cfg, **cfg.runlock)
```

When you run `python train.py --config config.yml`, Naga's resolvers will automatically:
1.  Find the file at `data/preprocessed/features.csv`.
2.  `runlock_data`: Hash the file and inject the hash into the `runlock.data.training_features` field.
3.  `runlock_prev`: Find the `run.lock` in the parent directory (`data/preprocessed/`) and embed it into the `runlock.prevs.preprocessing` field.

This approach keeps your configuration self-contained and your Python script cleaner and more focused on logic.

## Persisting Runs (Push/Pull)

For ultimate reproducibility and collaboration, especially across different machines, you need a way to persist and retrieve the exact state of a run—both the code and the data. Naga proposes a workflow for "pushing" and "pulling" runs.

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
