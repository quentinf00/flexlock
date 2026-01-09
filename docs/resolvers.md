# OmegaConf Resolvers

FlexLock registers custom OmegaConf resolvers for dynamic configuration values.

## Available Resolvers

### `${track:path}` - Hash Data Files

Compute and return the hash of a data file or directory.

**Usage:**
```yaml
_target_: myproject.train
input_data: data/train.csv
data_hash: ${track:${input_data}}  # Computes hash of data/train.csv
```

**Python:**
```python
from flexlock import py2cfg

cfg = py2cfg(
    train,
    input_data='data/train.csv',
    data_hash='${track:${input_data}}'
)
```

**Behavior:**
- For files: Computes XXHash (fast) or MD5 (fallback)
- For directories: Recursively hashes all files
- Uses SQLite cache (keyed by path + mtime) for speed
- Returns hash string (e.g., `"xxh64_abc123..."`)

**Use cases:**
- Verify data hasn't changed
- Include data version in experiment tags
- Detect data corruption

---

### `${stage:path}` - Load Previous Stage Info

Load configuration or results from a previous FlexLock run.

**Usage:**
```yaml
_target_: myproject.train
preprocess_dir: outputs/preprocess/run_001
preprocess_config: ${stage:${preprocess_dir}}  # Loads run.lock
```

**Returns:** Dictionary with keys:
- `config`: Configuration from previous stage
- `timestamp`: When it was run
- `repos`: Git repo info
- `data`: Data hashes

**Example:**
```python
from omegaconf import OmegaConf

cfg_str = """
train:
  preprocess_dir: outputs/preprocess/run_001
  upstream_lr: ${stage:${preprocess_dir}.config.learning_rate}
"""

cfg = OmegaConf.create(cfg_str)
print(cfg.train.upstream_lr)  # Retrieves lr from previous run's config
```

**Use cases:**
- Pipeline stage dependencies
- Inherit parameters from upstream stages
- Validate pipeline consistency

---

### `${now:format}` - Current Timestamp

Get current timestamp in specified format.

**Usage:**
```yaml
_target_: myproject.train
save_dir: outputs/train_${now:%Y%m%d_%H%M%S}
```

**Python:**
```python
cfg = py2cfg(
    train,
    save_dir='outputs/train_${now:%Y%m%d_%H%M%S}'
)
```

**Format strings:**
- `%Y`: 4-digit year (2024)
- `%m`: 2-digit month (01-12)
- `%d`: 2-digit day (01-31)
- `%H`: 2-digit hour (00-23)
- `%M`: 2-digit minute (00-59)
- `%S`: 2-digit second (00-59)

**Examples:**
```yaml
timestamp: ${now:%Y-%m-%d %H:%M:%S}  # "2024-01-15 14:30:00"
run_id: ${now:%y%m%d%H%M}            # "2401151430"
date: ${now:%Y%m%d}                  # "20240115"
```

---

### `${latest:glob}` - Find Latest Path

Find the most recently modified path matching a glob pattern.

**Usage:**
```yaml
_target_: myproject.eval
model_dir: ${latest:outputs/train_*/}
```

**Python:**
```python
cfg = py2cfg(
    evaluate,
    model_dir='${latest:outputs/train_*}'
)
```

**Behavior:**
- Expands glob pattern (uses `pathlib.Path.glob()`)
- Sorts by modification time (most recent first)
- Returns string path of latest match
- Raises error if no matches found

**Examples:**
```yaml
# Latest checkpoint
checkpoint: ${latest:checkpoints/epoch_*.pth}

# Latest experiment run
prev_run: ${latest:outputs/experiments/run_*/}

# Latest data file
data_file: ${latest:data/processed_*.csv}
```

---

### `${vinc:path}` - Version Increment

Generate next version number for a directory path.

**Usage:**
```yaml
_target_: myproject.train
save_dir: ${vinc:outputs/pipeline/run}
```

**Behavior:**
- Searches for existing directories matching `{path}_*`
- Finds highest numeric suffix
- Returns `{path}_{n+1}` where n is the highest existing

**Examples:**

Existing directories:
```
outputs/pipeline/
  run_0001/
  run_0002/
  run_0005/
```

Config:
```yaml
save_dir: ${vinc:outputs/pipeline/run}
```

Resolves to:
```
outputs/pipeline/run_0006/
```

**Use cases:**
- Auto-versioned experiment directories
- Sequential pipeline runs
- Avoid overwriting previous results

---

## Using Resolvers

### In YAML Configs

```yaml
# config.yaml
_target_: myproject.train

# Dynamic timestamp
save_dir: outputs/train_${now:%Y%m%d_%H%M%S}

# Data tracking
input_data: data/train.csv
data_version: ${track:${input_data}}

# Latest model
pretrained_model: ${latest:models/pretrained_*.pth}

# Versioned output
results_dir: ${vinc:outputs/results/exp}
```

### In Python Configs

```python
from flexlock import py2cfg
from omegaconf import OmegaConf

cfg = py2cfg(
    train,
    save_dir='outputs/train_${now:%Y%m%d_%H%M%S}',
    input_data='data/train.csv',
    data_version='${track:${input_data}}'
)

# Resolve all interpolations
resolved = OmegaConf.to_container(cfg, resolve=True)
print(resolved['data_version'])  # "xxh64_abc123..."
```

### In Decorator

```python
from flexlock import flexcli, py2cfg

@flexcli(
    save_dir='outputs/train_${now:%Y%m%d_%H%M%S}',
    snapshot_config=dict(
        repos={'main': '.'},
        data={'input': '${...input_path}'}
    )
)
def train(input_path, save_dir=None):
    print(f"Saving to {save_dir}")  # Auto-resolved
```

---

## Advanced Usage

### Nested Resolvers

```yaml
# Chain resolvers
latest_data_hash: ${track:${latest:data/processed_*.csv}}

# Use in paths
checkpoint: ${latest:${base_dir}/checkpoints/epoch_*.pth}
```

### Conditional Logic

```yaml
# Use OmegaConf's oc.select for conditionals
data_path: ${oc.select:custom_data_path,${latest:data/default_*.csv}}
```

### Pipeline Dependencies

```yaml
# Stage 1: Preprocess
preprocess:
  _target_: myproject.preprocess
  save_dir: ${vinc:outputs/preprocess/run}

# Stage 2: Train (depends on Stage 1)
train:
  _target_: myproject.train
  preprocess_dir: ${latest:outputs/preprocess/run_*/}
  preprocess_hash: ${track:${preprocess_dir}}
  upstream_config: ${stage:${preprocess_dir}}
  save_dir: ${vinc:outputs/train/run}
```

**Execution:**
```python
proj = Project(defaults='pipeline.defaults')

# Run preprocess
prep_result = proj.submit(proj.get('preprocess'))

# Train automatically finds latest preprocess output
train_result = proj.submit(proj.get('train'))
```

---

## Custom Resolvers

Register your own resolvers:

```python
from omegaconf import OmegaConf

def my_resolver(value: str) -> str:
    return value.upper()

# Register resolver
OmegaConf.register_new_resolver("upper", my_resolver)

# Use in config
cfg = OmegaConf.create({
    "name": "model",
    "NAME": "${upper:${name}}"
})

print(cfg.NAME)  # "MODEL"
```

**Examples:**

```python
# Environment variable resolver
import os
OmegaConf.register_new_resolver("env", lambda var: os.getenv(var))

# Usage: ${env:HOME}

# Math resolver
OmegaConf.register_new_resolver("mul", lambda a, b: float(a) * float(b))

# Usage: warmup_steps: ${mul:${total_steps},0.1}

# Path join resolver
from pathlib import Path
OmegaConf.register_new_resolver(
    "join",
    lambda *parts: str(Path(*parts))
)

# Usage: model_path: ${join:${base_dir},models,best.pth}
```

---

## Best Practices

### 1. Use `${track:...}` for Data Inputs

```python
# Good: Track data dependencies
cfg = py2cfg(
    train,
    input_data='data/train.csv',
    snapshot_config=dict(
        data={'train': '${...input_data}'}
    )
)

# Bad: No tracking
cfg = py2cfg(train, input_data='data/train.csv')
```

### 2. Use `${vinc:...}` for Sequential Runs

```python
# Good: Auto-versioning
cfg = py2cfg(train, save_dir='${vinc:outputs/exp/run}')

# Bad: Manual versioning (error-prone)
cfg = py2cfg(train, save_dir='outputs/exp/run_0042')
```

### 3. Use `${latest:...}` for Pipeline Stages

```python
# Good: Automatically finds latest upstream
train_cfg = py2cfg(
    train,
    preprocess_dir='${latest:outputs/preprocess/run_*}'
)

# Bad: Hardcoded path (breaks when preprocess reruns)
train_cfg = py2cfg(train, preprocess_dir='outputs/preprocess/run_0001')
```

### 4. Combine Resolvers for Powerful Patterns

```yaml
# Auto-versioned run with timestamp in name
save_dir: ${vinc:outputs/train_${now:%Y%m%d}/run}

# Latest data file with version tracking
input_data: ${latest:data/processed_*.csv}
data_hash: ${track:${input_data}}

# Pipeline stage with dependency tracking
upstream_dir: ${latest:outputs/stage1/run_*/}
upstream_config: ${stage:${upstream_dir}}
upstream_lr: ${stage:${upstream_dir}.config.lr}
```

---

## See Also

- [OmegaConf Documentation](https://omegaconf.readthedocs.io/) - Interpolation syntax
- [Snapshot System](./snapshot.md) - How `${track:...}` integrates with snapshots
- [Python API](./python_api.md) - Using resolvers programmatically
- [CLI Reference](./cli_reference.md) - Resolver usage in CLI workflows
