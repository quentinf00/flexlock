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

@flexcli(default_config=Config)
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
def snapshot_resolver(path: str, key: str | None = None, *, _root_: DictConfig) -> str:
    item = path if key is None else {key: path}
    snapshot(
        config=_root_,
        data=item,
        prevs=[path],
        merge=True,
        mlflowlink=False,
        resolve=False,
    )
    return path
```

This approach keeps your configuration self-contained and your Python script cleaner and more focused on logic.

