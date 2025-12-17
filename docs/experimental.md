# Advanced Features

This section covers advanced features of FlexLock that provide more power and flexibility for complex workflows.

## OmegaConf Resolvers

FlexLock registers custom [OmegaConf](https://omegaconf.readthedocs.io/) resolvers that provide powerful dynamic configuration capabilities. These resolvers are automatically registered when you import flexlock and can be used in YAML configuration files.

### Overview

Resolvers allow you to dynamically compute or fetch values directly in your configuration files using the syntax: `${resolver_name:arg1,arg2}`.

**Benefits:**
- **Declarative configurations**: Keep logic in config files rather than Python code
- **Reproducibility**: Automatic timestamping, versioning, and data tracking
- **Pipeline chaining**: Link stages together seamlessly
- **Cleaner code**: Reduce boilerplate in Python scripts

---

## Available Resolvers

### 1. `now` - Timestamp Generation

Returns the current timestamp as a formatted string.

**Syntax:** `${now:}` or `${now:format_string}`

**Parameters:**
- `format_string` (optional): strftime format string. Default: `"%Y-%m-%d_%H-%M-%S"`

**Examples:**

```yaml
# Default format (YYYY-MM-DD_HH-MM-SS)
save_dir: results/run_${now:}
# Result: results/run_2025-12-16_14-30-45

# Custom format - date only
experiment_id: exp_${now:%Y%m%d}
# Result: exp_20251216

# Custom format - full timestamp
log_file: logs/${now:%Y-%m-%d/%H%M%S}.log
# Result: logs/2025-12-16/143045.log
```

**Use Cases:**
- Creating timestamped output directories
- Generating unique run identifiers
- Organizing experiments by date/time
- Ensuring runs don't overwrite each other

---

### 2. `vinc` - Version Increment

Finds the highest existing version number and returns the next versioned path. This is useful for sequential experiment numbering without overwriting previous runs.

**Syntax:** `${vinc:base_path}` or `${vinc:base_path,format}`

**Parameters:**
- `base_path`: Base directory path (searches for existing versions)
- `format` (optional): Format string for version suffix. Default: `"_{i:04d}"` (e.g., `_0001`, `_0002`)

**Examples:**

```yaml
# Default format (_0001, _0002, _0003, ...)
save_dir: results/experiment${vinc:}
# If experiment_0001 and experiment_0002 exist → creates experiment_0003

# Custom format with different padding
output_path: outputs/run${vinc:,_v{i:02d}}
# Creates: run_v01, run_v02, run_v03, ...

# Custom format with prefix
model_dir: models/checkpoint${vinc:,_{i:03d}}
# Creates: checkpoint_001, checkpoint_002, ...
```

**How It Works:**
1. Searches for existing paths matching the pattern
2. Extracts version numbers from existing paths
3. Returns the next sequential number
4. Creates directory automatically

**Use Cases:**
- Sequential experiment numbering
- Automatic versioning without overwriting
- Organized experiment progression
- Resume-friendly workflows

**Note:** If no existing versions are found, starts at 1 (or the format's starting value).

---

### 3. `latest` - Latest Path Resolution

Returns the most recently modified path matching a glob pattern.

**Syntax:** `${latest:glob_pattern}`

**Parameters:**
- `glob_pattern`: Glob pattern to match files/directories

**Examples:**

```yaml
# Use output from most recent preprocessing run
input_data: ${latest:data/preprocess_*/output.csv}
# If data/preprocess_0001/output.csv and data/preprocess_0002/output.csv exist
# → Returns data/preprocess_0002/output.csv (most recent)

# Chain experiments together automatically
model_checkpoint: ${latest:models/train_*/best_model.pt}

# Reference latest log file
previous_log: ${latest:logs/*.log}

# Combine with other paths
eval_input: ${latest:results/exp_*/predictions.json}
```

**How It Works:**
1. Expands the glob pattern to find matching paths
2. Sorts matches by modification time (most recent first)
3. Returns the newest path
4. If no matches found, returns the original pattern string

**Use Cases:**
- **Pipeline chaining**: Automatically use output from the previous stage
- **Incremental development**: Always work with latest data
- **Resuming workflows**: Reference most recent checkpoint

**Important Notes:**
- Returns path as string; ensure the file exists before using
- Uses filesystem modification time for sorting
- Returns the glob pattern unchanged if no matches found

---

### 4. `track` - Data Hash Computation

Computes and returns the hash of a file or directory. This is useful for tracking data provenance without creating a full snapshot.

**Syntax:** `${track:path}`

**Parameters:**
- `path`: Path to file or directory to hash

**Examples:**

```yaml
# Track input data hash for provenance
dataset:
  path: data/train.csv
  hash: ${track:data/train.csv}
# hash field will contain: "abc123def456..."

# Track multiple data sources
config:
  train_data: data/train.csv
  train_hash: ${track:data/train.csv}
  test_data: data/test.csv
  test_hash: ${track:data/test.csv}

# Use in conditional logic (with OmegaConf)
data_version: ${track:data/input.csv}
```

**How It Works:**
- **Files**: Computes xxHash of file contents
- **Directories**: Recursively hashes directory tree structure + file hashes
- **Caching**: Results cached in `~/.cache/flexlock/hashes.db` for performance
- **Deterministic**: Same content always produces same hash

**Use Cases:**
- Computing data hashes without full snapshot
- Verifying data integrity in configs
- Custom provenance tracking
- Data versioning in configuration

**Performance:**
- First hash of large data may take time
- Subsequent hashes are instant (cached)
- Cache based on path + size + modification time

**See also:** [Data Hashing System](./snapshot.md#data-hashing-system) for more details.

---

### 5. `stage` - Load Previous Stage

Loads a previous stage's `run.lock` file and returns its contents as a dictionary.

**Syntax:** `${stage:path_to_directory}`

**Parameters:**
- `path_to_directory`: Path to directory containing a `run.lock` file

**Examples:**

```yaml
# Load entire preprocessing stage metadata
preprocessing: ${stage:data/preprocess_0001}
# preprocessing will contain the full run.lock contents as dict

# Access nested values from previous stage
prev_config: ${stage:../preprocessing}.config
prev_data_hash: ${stage:../preprocessing}.data.training_data

# Use in configuration inheritance
training:
  # Inherit preprocessing parameters
  input_data: ${stage:data/preprocess_0001}.config.output_path
  batch_size: ${stage:data/preprocess_0001}.config.batch_size
```

**How It Works:**
1. Looks for `run.lock` file in specified directory
2. Loads and parses the lock file (YAML format)
3. Returns contents as OmegaConf DictConfig
4. Allows nested access using dot notation

**Use Cases:**
- **Multi-stage pipelines**: Reference outputs and configs from upstream stages
- **Lineage tracking**: Inherit parameters from previous experiments
- **Reproducibility**: Ensure consistency across pipeline stages
- **Configuration inheritance**: Build on previous configurations

**Example Pipeline:**

```yaml
# Stage 1: Preprocessing (run first)
# preprocess_config.yml
save_dir: data/preprocess_${vinc:}
output_file: output.csv
```

```yaml
# Stage 2: Training (references stage 1)
# train_config.yml
save_dir: results/train_${vinc:}

# Load preprocessing config and data
preprocessing: ${stage:${latest:data/preprocess_*}}
input_data: ${preprocessing}.config.save_dir}/${preprocessing}.config.output_file}
data_hash: ${preprocessing}.data.training_data}

# Inherit preprocessing parameters
feature_columns: ${preprocessing}.config.feature_columns}
```

---

### 6. `snapshot` - Declarative Snapshot Registration

Adds a path to the snapshot's data and prevs sections declaratively, returning the path. This makes snapshot tracking part of your configuration rather than Python code.

**Syntax:** `${snapshot:path}` or `${snapshot:path,key_name}`

**Parameters:**
- `path`: Path to file or directory to track
- `key_name` (optional): Name for this entry in the snapshot

**Examples:**

```yaml
# Basic usage - track the path
training_data: ${snapshot:data/features.csv}
# Returns: "data/features.csv"
# Side effect: Adds to snapshot data + prevs sections

# With named key in snapshot
training_data: ${snapshot:data/features.csv,training_features}
# Returns: "data/features.csv"
# In run.lock: data.training_features = hash(data/features.csv)

# Track multiple data sources
config:
  train: ${snapshot:data/train.csv,train}
  val: ${snapshot:data/val.csv,validation}
  test: ${snapshot:data/test.csv,test}
```

**How It Works:**

When the resolver is evaluated, it automatically:
1. Computes the hash of the specified path
2. Adds it to the snapshot's `data` section
3. Searches for a `run.lock` file in that directory
4. If found, adds it to the snapshot's `prevs` (lineage) section
5. Returns the path as a string

**Under the hood:**
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

**Detailed Example:**

```yaml
# config.yml
save_dir: results/training
model:
  type: mlp
  layers: 3

# Declaratively track data dependencies
training_data: ${snapshot:data/processed/features.csv,features}
validation_data: ${snapshot:data/processed/validation.csv,validation}

# Optional: explicit snapshot configuration
_snapshot_:
  repos:
    main: "."
```

```python
# train.py
from flexlock import flexcli, snapshot
from omegaconf import DictConfig

@flexcli
def main(cfg: DictConfig):
    # Your training logic
    model = train_model(cfg.training_data, cfg.validation_data)

    # Snapshot automatically includes resolved data from config
    snapshot(cfg)
```

**Resulting `run.lock`:**
```yaml
timestamp: "2025-12-16 14:30:45"
config:
  save_dir: results/training
  model:
    type: mlp
    layers: 3
  training_data: data/processed/features.csv
  validation_data: data/processed/validation.csv

data:
  features: abc123...  # Hash of data/processed/features.csv
  validation: def456...  # Hash of data/processed/validation.csv

prevs:
  # If data/processed/ had a run.lock, it would be listed here

repos:
  main:
    commit: xyz789...
    tree_hash: ...
```

**Why Use This:**
- **Declarative**: Snapshot tracking defined in config, not code
- **Self-contained**: Config files are complete specifications
- **Cleaner Python**: Less boilerplate in scripts
- **Explicit dependencies**: Data requirements visible in config

**Comparison:**

*Imperative (traditional):*
```python
@flexcli
def main(cfg):
    snapshot(cfg, data={
        "features": "data/processed/features.csv",
        "validation": "data/processed/validation.csv"
    })
```

*Declarative (using resolver):*
```yaml
training_data: ${snapshot:data/processed/features.csv,features}
validation_data: ${snapshot:data/processed/validation.csv,validation}
```
```python
@flexcli
def main(cfg):
    snapshot(cfg)  # Data already tracked from config!
```

---

## Combining Resolvers

Resolvers can be composed together for powerful workflows:

### Example 1: Latest + Snapshot
Automatically use the most recent preprocessing output and track it:

```yaml
input_data: ${snapshot:${latest:data/preprocess_*/output.csv},preprocessing_output}
```

**What happens:**
1. `${latest:...}` finds most recent preprocessing output
2. `${snapshot:...,preprocessing_output}` tracks it in the snapshot
3. Result: Uses latest data AND tracks it for reproducibility

### Example 2: Stage + Latest
Load config from most recent preprocessing run:

```yaml
preprocess: ${stage:${latest:data/preprocess_*}}
input_file: ${preprocess}.config.output_file}
```

### Example 3: Now + Vinc
Combine timestamp with version number:

```yaml
save_dir: results/${now:%Y%m%d}/exp${vinc:,_{i:03d}}
# Result: results/20251216/exp_001
```

### Example 4: Complex Pipeline
Complete pipeline with chained resolvers:

```yaml
# training_config.yml
experiment:
  name: training_${now:%Y%m%d}
  save_dir: results/${now:%Y%m%d}/run${vinc:,_{i:03d}}

  # Find and load latest preprocessing
  preprocessing: ${stage:${latest:data/preprocess_*}}

  # Use preprocessing output
  input_data: ${snapshot:${preprocessing}.config.save_dir}/output.csv,train_data}

  # Reference preprocessing parameters
  feature_dim: ${preprocessing}.config.n_features}

  _snapshot_:
    repos:
      main: "."
```

---

## Configuration via `_snapshot_` Section

You can declare snapshot tracking directly in your YAML configuration using the special `_snapshot_` section:

### Basic Example

```yaml
# config.yml
experiment:
  param: 100
  save_dir: results/exp

  _snapshot_:
    repos:
      main: "."
      library: "../mylib"
    data:
      training: data/train.csv
      test: data/test.csv
    prevs:
      - data/preprocess_0001
```

### How It Works

When you use `@flexcli` or `FlexLockRunner`, the `_snapshot_` section is:
1. **Extracted** from the config
2. **Passed to `snapshot()`** automatically
3. **Removed** from the config passed to your function

**Python code stays clean:**

```python
from flexlock import flexcli, snapshot

@flexcli
def main(cfg):
    # Just do your work
    train_model(cfg)

    # Snapshot uses _snapshot_ section from config
    snapshot(cfg)
```

### _snapshot_ Parameters

The `_snapshot_` section supports all `snapshot()` parameters:

```yaml
_snapshot_:
  # Track git repositories
  repos:
    main: "."
    shared_lib: "../libs/shared"

  # Track data files/directories
  data:
    training: data/train.csv
    validation: data/val.csv
    model_weights: models/pretrained.pt

  # Track previous stages (lineage)
  prevs:
    - data/preprocess_0001
    - results/pretrain_0005

  # Optional: parent lock for delta snapshots
  parent_lock: results/master_run/run.lock
```

### Combining _snapshot_ with Resolvers

You can use resolvers within the `_snapshot_` section:

```yaml
_snapshot_:
  repos:
    main: "."

  data:
    # Use latest data automatically
    input: ${latest:data/preprocessed_*/output.csv}

    # Track specific version
    labels: data/labels_v${now:%Y%m%d}.csv

  prevs:
    # Reference latest preprocessing run
    - ${latest:data/preprocess_*}
```

### When to Use

**Use `_snapshot_` section when:**
- You want snapshot config in YAML (declarative)
- Different configs need different tracking
- Snapshot params change across experiments

**Use `snapshot()` parameters when:**
- Snapshot config is constant across runs
- You need dynamic snapshot logic in Python
- You're migrating existing code

Both approaches work well and can be mixed!

---

## Best Practices

### 1. Use Descriptive Keys

```yaml
# Good: Clear what each entry represents
training_data: ${snapshot:data/train.csv,training_features}
test_data: ${snapshot:data/test.csv,test_features}

# Avoid: Generic keys
data1: ${snapshot:data/train.csv}
data2: ${snapshot:data/test.csv}
```

### 2. Combine Latest with Snapshot

Always track data found with `${latest:}`:

```yaml
# Good: Tracked for reproducibility
input: ${snapshot:${latest:data/preprocess_*/out.csv},input}

# Avoid: Not tracked (hard to reproduce later)
input: ${latest:data/preprocess_*/out.csv}
```

### 3. Use Vinc for Sequential Experiments

```yaml
# Good: Sequential numbering
save_dir: results/exp${vinc:}

# Avoid: May overwrite previous runs
save_dir: results/exp_final
```

### 4. Document Complex Resolver Chains

```yaml
# Load latest preprocessing and extract config
preprocessing: ${stage:${latest:data/preprocess_*}}  # Find latest preprocess run
input_data: ${preprocessing}.config.output_path}      # Extract output path from it
```

---

## Summary

FlexLock provides 6 powerful resolvers:

| Resolver | Purpose | Example |
|----------|---------|---------|
| `now` | Timestamps | `${now:%Y%m%d}` → `20251216` |
| `vinc` | Version increment | `${vinc:}` → `_0001`, `_0002`, ... |
| `latest` | Latest path | `${latest:data/*/out.csv}` → most recent |
| `track` | Data hash | `${track:data/train.csv}` → `abc123...` |
| `stage` | Load previous | `${stage:prev_run}` → prev run.lock dict |
| `snapshot` | Declarative tracking | `${snapshot:data.csv,key}` → tracks data |

**Key Benefits:**
- **Declarative configs**: Move logic from Python to YAML
- **Automatic tracking**: Snapshot data dependencies in config
- **Pipeline chaining**: Link stages seamlessly with `stage` and `latest`
- **Reproducibility**: Automatic versioning and timestamping
- **Cleaner code**: Less boilerplate in Python scripts

These resolvers make FlexLock configurations more powerful while keeping your Python code focused on logic rather than tracking infrastructure.
