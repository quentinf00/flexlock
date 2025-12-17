# FlexLockRunner: Advanced CLI System

FlexLockRunner provides a more powerful and flexible alternative to the `@flexcli` decorator, offering advanced sweep capabilities, flexible configuration management, and fine-grained control over experiment execution.

## When to Use FlexLockRunner

**Use FlexLockRunner when you need:**
- Complex sweep configurations (grids, lists from files, inline sweeps)
- Multi-stage configuration selection with node picking
- Advanced override mechanisms (pre-select and post-select)
- Python-based configuration defaults from modules
- Programmatic experiment execution
- Run existence checking to skip duplicates
- Declarative snapshot configuration in YAML

**Use `@flexcli` when:**
- You want a simple, decorator-based interface
- Basic task-based parallelization is sufficient
- Your experiments have straightforward configurations

**Rule of thumb:** Start with `@flexcli` for simple scripts. Graduate to FlexLockRunner when you need more power.

---

## Basic Usage

### Python API

The simplest way to use FlexLockRunner:

```python
# my_experiment.py
from flexlock import FlexLockRunner

if __name__ == "__main__":
    runner = FlexLockRunner()
    runner.run()
```

Run with a config file:

```bash
python my_experiment.py --config configs/experiment.yml
```

### Direct Instantiation

For more control:

```python
from flexlock import FlexLockRunner

def train(cfg):
    """Training function."""
    print(f"Training with config: {cfg}")
    # Your training logic here

if __name__ == "__main__":
    runner = FlexLockRunner()
    runner.run()  # Will call train() with the loaded config
```

**How it works:**
1. FlexLockRunner builds a config from CLI arguments
2. Looks for a function to execute in the current module
3. Calls the function with the config

### Standalone CLI: flexlock-run

For convenience, FlexLock provides a standalone CLI command that doesn't require creating a Python script:

```bash
# Run directly with a config file
flexlock-run --config experiments.yml

# With defaults from Python module
flexlock-run --defaults mypackage.config:defaults --config exp.yml

# Select specific experiment
flexlock-run --config experiments.yml --select experiments.baseline

# Run a sweep
flexlock-run --config base.yml --sweep-file sweep.yaml --n_jobs 4

# Quick parameter sweep
flexlock-run --config base.yml --sweep "0.001,0.01,0.1" --sweep-target lr
```

**When to use `flexlock-run`:**
- Quick experiments without writing Python scripts
- Testing configurations before integrating into code
- Running one-off experiments
- Shell script automation
- CI/CD pipelines where you just need to run configs

**Note:** The `flexlock-run` command uses FlexLockRunner internally, so all FlexLockRunner features (sweeps, node selection, overrides) are available.

**Config requirement:** Your config must include a `_target_` key that specifies which function or class to instantiate:

```yaml
# experiment.yml
_target_: mypackage.train.main  # Function to call

model:
  type: mlp
  hidden_size: 128
training:
  lr: 0.001
  epochs: 100
save_dir: results/quick_test
```

**Example workflow:**

```bash
# 1. Create your training function
# mypackage/train.py
def main(model, training, save_dir):
    print(f"Training {model['type']} model")
    print(f"Learning rate: {training['lr']}")
    # Your training logic...

# 2. Create a config file with _target_
cat > experiment.yml <<EOF
_target_: mypackage.train.main

model:
  type: mlp
  hidden_size: 128
training:
  lr: 0.001
  epochs: 100
save_dir: results/quick_test
EOF

# 3. Run directly with flexlock-run
flexlock-run --config experiment.yml

# 4. Override parameters
flexlock-run --config experiment.yml -O training.lr=0.01

# 5. Run a sweep
echo "0.001\n0.01\n0.1" > lrs.txt
flexlock-run --config experiment.yml --sweep-file lrs.txt --sweep-target training.lr --n_jobs 3
```

**Alternative: Using `py2cfg` for automatic `_target_` generation:**

```python
# mypackage/config.py
from flexlock import py2cfg

def train(model_type: str = "mlp", lr: float = 0.001, save_dir: str = "results"):
    print(f"Training {model_type} with lr={lr}")
    # Your training logic...

# Generate config with _target_ automatically
defaults = py2cfg(train)
```

```bash
# Use the auto-generated config
flexlock-run --defaults mypackage.config:defaults -O lr=0.01
```

---

## Configuration Loading

FlexLockRunner uses a **layered configuration system** that allows you to build complex configurations from multiple sources.

### Four-Layer System

Configurations are built in this order (later layers override earlier ones):

```
1. Python Defaults (--defaults)
     ↓
2. Base Config File (--config)
     ↓
3. Node Selection (--select)
     ↓
4. Overrides (--overrides, --merge)
```

Let's explore each layer in detail.

---

### Layer 1: Python Defaults

Define structured defaults in Python modules:

**File: `configs/defaults.py`**
```python
defaults = {
    "model": {
        "type": "mlp",
        "hidden_size": 128,
        "num_layers": 2
    },
    "training": {
        "lr": 0.001,
        "epochs": 10,
        "batch_size": 32
    },
    "save_dir": "results/experiment"
}
```

**Usage:**
```bash
python script.py --defaults configs.defaults:defaults
```

**Syntax:** `module.path:variable_name`

**Why use Python defaults:**
- Type-safe with IDE support
- Can compute values dynamically
- Easy to share across projects
- Version controlled with code

---

### Layer 2: Base Config File

YAML configuration file that builds on or overrides defaults:

**File: `experiment.yml`**
```yaml
model:
  hidden_size: 256  # Override default

training:
  lr: 0.01  # Override default

save_dir: results/my_experiment  # Override default
```

**Usage:**
```bash
python script.py --defaults configs.defaults:defaults --config experiment.yml
```

**Result:** Merges YAML config into Python defaults.

**You can also use config without defaults:**
```bash
python script.py --config experiment.yml
```

---

### Layer 3: Node Selection

Select a specific subtree from your configuration:

**File: `experiments.yml`**
```yaml
experiments:
  baseline:
    param: 10
    model: "small"
    save_dir: results/baseline

  large_model:
    param: 20
    model: "large"
    save_dir: results/large

  ablation:
    param: 5
    model: "small"
    save_dir: results/ablation
```

**Select specific experiment:**
```bash
# Run just baseline
python script.py --config experiments.yml --select experiments.baseline

# Run large_model
python script.py --config experiments.yml --select experiments.large_model
```

**What happens:**
1. Loads full config from `experiments.yml`
2. Extracts the `experiments.baseline` subtree
3. Uses that as the config for the run

**Dot notation for nested selection:**
```yaml
project:
  experiments:
    phase1:
      exp1: {...}
      exp2: {...}
```

```bash
python script.py --config proj.yml --select project.experiments.phase1.exp1
```

---

### Layer 4: Overrides

Two types of overrides: **before selection** and **after selection**.

#### Before Selection (Root Overrides)

Applied before `--select` extracts a subtree:

**Flags:**
- `--overrides` / `-o`: Dot-list overrides (e.g., `key.subkey=value`)
- `--merge` / `-m`: Merge a YAML file at root level

**Example:**
```bash
# Override before selection
python script.py \
  --config experiments.yml \
  --overrides experiments.baseline.param=100 \
  --select experiments.baseline
```

**Use case:** Modify config before selecting a node.

#### After Selection (Node Overrides)

Applied after `--select` extracts a subtree:

**Flags:**
- `--overrides-after-select` / `-O`: Dot-list overrides on selected node
- `--merge-after-select` / `-M`: Merge a YAML file into selected node

**Example:**
```bash
# Override after selection
python script.py \
  --config experiments.yml \
  --select experiments.baseline \
  --overrides-after-select param=100
```

**Use case:** Override parameters in the selected experiment.

#### When to Use Each

```bash
# Before select: Modify the full config structure
--config multi.yml --overrides experiments.exp1.lr=0.1 --select experiments.exp1

# After select: Modify the selected experiment directly
--config multi.yml --select experiments.exp1 --overrides-after-select lr=0.1
```

For simple cases (single experiment in config), use `--overrides-after-select`.

---

### Complete Configuration Example

Combining all layers:

**Python defaults:**
```python
# configs/defaults.py
defaults = {
    "model": {"type": "mlp", "size": 128},
    "training": {"lr": 0.001, "epochs": 10}
}
```

**Base config:**
```yaml
# base.yml
training:
  epochs: 100  # Override default
```

**Experiments config:**
```yaml
# experiments.yml
experiments:
  exp1:
    training:
      lr: 0.01
    save_dir: results/exp1
  exp2:
    training:
      lr: 0.1
    save_dir: results/exp2
```

**Command:**
```bash
python script.py \
  --defaults configs.defaults:defaults \
  --config base.yml \
  --merge experiments.yml \
  --select experiments.exp1 \
  --overrides-after-select training.batch_size=64
```

**Resulting config:**
```yaml
model:
  type: mlp
  size: 128
training:
  lr: 0.01        # From experiments.exp1
  epochs: 100     # From base.yml
  batch_size: 64  # From override
save_dir: results/exp1  # From experiments.exp1
```

---

## Sweep Capabilities

FlexLockRunner provides three ways to define parameter sweeps:

### Overview

| Method | Flag | Use Case |
|--------|------|----------|
| Config Key | `--sweep-key` | Sweep list defined in config |
| File | `--sweep-file` | Sweep list in external YAML/JSON/TXT |
| CLI | `--sweep` | Quick inline sweeps |

All three methods support the `--sweep-target` flag to control where sweep values are injected.

---

### Sweep Method 1: From Config Key

Define sweep in your configuration file:

**File: `sweep_config.yml`**
```yaml
base:
  model:
    type: mlp
  save_dir: results/sweep

sweep_configs:
  - training.lr: 0.001
  - training.lr: 0.01
  - training.lr: 0.1
```

**Usage:**
```bash
python script.py \
  --config sweep_config.yml \
  --select base \
  --sweep-key sweep_configs \
  --n_jobs 3
```

**What happens:**
1. Loads `base` config
2. For each item in `sweep_configs`:
   - Merges sweep item into base config
   - Runs experiment
3. Runs 3 experiments in parallel

**Use case:** Keep sweep definitions with experiment configs.

---

### Sweep Method 2: From File

Define sweep in a separate file:

**YAML/JSON Format:**

**File: `sweep.yaml`**
```yaml
- learning_rate: 0.001
  batch_size: 32
- learning_rate: 0.01
  batch_size: 64
- learning_rate: 0.1
  batch_size: 128
```

**Usage:**
```bash
python script.py \
  --config base.yml \
  --sweep-file sweep.yaml \
  --n_jobs 3
```

Each dict is merged into the base config.

**Text File Format:**

**File: `learning_rates.txt`**
```
0.001
0.01
0.1
```

**Usage with sweep target:**
```bash
python script.py \
  --config base.yml \
  --sweep-file learning_rates.txt \
  --sweep-target training.lr \
  --n_jobs 3
```

**Use case:**
- YAML/JSON: Multi-parameter sweeps
- TXT: Simple 1D parameter sweeps

---

### Sweep Method 3: From CLI

Quick inline sweeps without creating files:

**Simple values:**
```bash
python script.py \
  --config base.yml \
  --sweep "1,2,3,4,5" \
  --sweep-target model.num_layers \
  --n_jobs 5
```

Runs 5 experiments with `model.num_layers` = 1, 2, 3, 4, 5.

**With key=value format:**
```bash
python script.py \
  --config base.yml \
  --sweep "lr=0.001,lr=0.01,lr=0.1" \
  --n_jobs 3
```

Each `lr=value` is parsed as `{"lr": value}` and merged into config.

**Type inference:**

FlexLockRunner automatically infers types:
```bash
--sweep "0.001,0.01,0.1"           # Parsed as floats
--sweep "1,2,3"                     # Parsed as ints
--sweep "true,false"                # Parsed as bools
--sweep "small,medium,large"        # Parsed as strings
```

**Use case:** Quick experiments without creating config files.

---

### Sweep Target

The `--sweep-target` flag controls where sweep values are injected into the config.

#### Without Sweep Target (Root Merge)

Each sweep item must be a dict and is merged at root level:

```bash
python script.py \
  --sweep-file sweep.yaml \
  --n_jobs 3
```

**sweep.yaml:**
```yaml
- training.lr: 0.001
  training.batch_size: 32
- training.lr: 0.01
  training.batch_size: 64
```

#### With Sweep Target (Value Injection)

Sweep items can be primitives and are injected at specified path:

```bash
python script.py \
  --sweep "0.001,0.01,0.1" \
  --sweep-target training.lr \
  --n_jobs 3
```

Equivalent to sweeping over:
```yaml
- training.lr: 0.001
- training.lr: 0.01
- training.lr: 0.1
```

**Use case:** Single-parameter sweeps without writing configs.

---

### Sweep Examples

#### Example 1: Hyperparameter Grid

**Generate grid in Python:**
```python
# generate_grid.py
import itertools
import yaml

lrs = [0.001, 0.01, 0.1]
batch_sizes = [32, 64, 128]

grid = [
    {"training.lr": lr, "training.batch_size": bs}
    for lr, bs in itertools.product(lrs, batch_sizes)
]

with open("grid.yaml", "w") as f:
    yaml.dump(grid, f)

print(f"Generated {len(grid)} experiments")
```

**Run sweep:**
```bash
python generate_grid.py  # Creates grid.yaml with 9 configs
python train.py --config base.yml --sweep-file grid.yaml --n_jobs 9
```

#### Example 2: Text File Sweep

**seeds.txt:**
```
42
123
456
789
1000
```

**Usage:**
```bash
python experiment.py \
  --config config.yml \
  --sweep-file seeds.txt \
  --sweep-target seed \
  --n_jobs 5
```

Runs 5 experiments with different random seeds in parallel.

#### Example 3: Model Architecture Sweep

**models.yaml:**
```yaml
- model.type: "small"
  model.hidden_size: 128
  model.num_layers: 2

- model.type: "medium"
  model.hidden_size: 256
  model.num_layers: 4

- model.type: "large"
  model.hidden_size: 512
  model.num_layers: 6
```

**Usage:**
```bash
python train.py --config base.yml --sweep-file models.yaml --n_jobs 3
```

---

## Declarative Snapshot Tracking

Configure snapshot tracking directly in YAML using the special `_snapshot_` section.

### Basic Usage

```yaml
# config.yml
experiment:
  param: 100
  save_dir: results/exp

  _snapshot_:
    repos:
      main: "."
    data:
      training: data/train.csv
      test: data/test.csv
    prevs:
      - data/preprocess_0001
```

### How It Works

When you run FlexLockRunner, the `_snapshot_` section is:
1. **Extracted** from the config
2. **Passed to `snapshot()`** automatically before your function runs
3. **Removed** from the config passed to your function

**Python code stays simple:**

```python
from flexlock import FlexLockRunner

def train(cfg):
    """Training function."""
    # Just use the config - snapshot is already handled
    model = build_model(cfg.experiment)
    train_model(model)

if __name__ == "__main__":
    runner = FlexLockRunner()
    runner.run()
```

### Supported Parameters

The `_snapshot_` section supports all parameters of the `snapshot()` function:

```yaml
_snapshot_:
  # Git repositories to track
  repos:
    main: "."
    shared_lib: "../libs/shared"

  # Data files/directories to hash
  data:
    training: data/train.csv
    validation: data/val.csv
    test: data/test.csv

  # Previous stages for lineage
  prevs:
    - data/preprocess_0001
    - results/pretrain_0005

  # Parent lock for delta snapshots
  parent_lock: results/master/run.lock
```

### Using Resolvers in _snapshot_

Combine declarative snapshots with [OmegaConf resolvers](./experimental.md):

```yaml
experiment:
  save_dir: results/train_${vinc:}

  _snapshot_:
    repos:
      main: "."

    data:
      # Track latest preprocessing output
      input: ${latest:data/preprocessed_*/output.csv}

      # Track with timestamp
      labels: data/labels_${now:%Y%m%d}.csv

    prevs:
      # Reference latest preprocessing run
      - ${latest:data/preprocess_*}
```

**See also:** [Resolvers documentation](./experimental.md) for more on `${latest:}`, `${vinc:}`, etc.

---

## Check If Run Exists

Skip runs that already exist to avoid recomputing results:

```bash
python script.py --config exp.yml --check-exists
```

### How It Works

1. Loads the configuration
2. Looks for existing `run.lock` in `save_dir`
3. Compares config in `run.lock` with current config
4. If configs match: **skips run**
5. If configs differ: **runs experiment**

### Use Case: Resuming Interrupted Sweeps

```bash
# Start sweep
python train.py --sweep-file sweep.yaml --n_jobs 4 --check-exists

# If interrupted (Ctrl+C or system failure), just rerun:
python train.py --sweep-file sweep.yaml --n_jobs 4 --check-exists
# Completed tasks are automatically skipped!
```

### What Gets Compared

The `--check-exists` flag compares:
- Configuration parameters
- Data hashes (if tracked)
- Git state (commit/tree hashes)

**Does NOT compare:**
- `save_dir` path (expected to be the same)
- Timestamps (always different)
- Results/outputs

### Example Output

```bash
$ python train.py --config exp.yml --check-exists

Checking if run exists at: results/exp_0001
✓ Run already exists with matching config. Skipping.
```

```bash
$ python train.py --config exp.yml --check-exists

Checking if run exists at: results/exp_0002
✗ No existing run found. Running experiment...
```

---

## Complete Examples

### Example 1: Simple Training Script

**train.py:**
```python
from flexlock import FlexLockRunner
from omegaconf import DictConfig

def train(cfg: DictConfig):
    """Train a model."""
    print(f"Training with LR: {cfg.training.lr}")
    print(f"Model type: {cfg.model.type}")

    # Your actual training code here
    # model = build_model(cfg.model)
    # trainer = Trainer(cfg.training)
    # trainer.train(model)

    print(f"Results saved to: {cfg.save_dir}")

if __name__ == "__main__":
    runner = FlexLockRunner()
    runner.run()
```

**config.yml:**
```yaml
model:
  type: mlp
  hidden_size: 256

training:
  lr: 0.001
  epochs: 100
  batch_size: 32

save_dir: results/experiment
```

**Run:**
```bash
python train.py --config config.yml
```

---

### Example 2: Hyperparameter Sweep

**hp_sweep.yml:**
```yaml
base:
  model:
    type: mlp
    hidden_size: 128
  training:
    epochs: 100
    batch_size: 32
  save_dir: results/hp_sweep

  _snapshot_:
    repos:
      main: "."
    data:
      training: data/train.csv

learning_rates:
  - training.lr: 0.001
  - training.lr: 0.01
  - training.lr: 0.1
```

**train.py:**
```python
from flexlock import FlexLockRunner, snapshot
from omegaconf import DictConfig

def train(cfg: DictConfig):
    print(f"Training with LR: {cfg.training.lr}")

    # Your training logic
    # ...

    # Snapshot is created automatically from _snapshot_ section
    snapshot(cfg)

if __name__ == "__main__":
    runner = FlexLockRunner()
    runner.run()
```

**Run sweep:**
```bash
python train.py \
  --config hp_sweep.yml \
  --select base \
  --sweep-key learning_rates \
  --n_jobs 3
```

**Results:**
```
results/hp_sweep/
├── run.lock              # Master snapshot
├── run.lock.tasks.db     # Task database
└── run.lock.tasks        # Task results (YAML)
```

---

### Example 3: Cross-Product Grid Search

**Generate grid:**
```python
# generate_grid.py
import itertools
import yaml

# Define parameter ranges
learning_rates = [0.001, 0.01, 0.1]
batch_sizes = [32, 64, 128]
hidden_sizes = [128, 256, 512]

# Create cross-product
grid = [
    {
        "training.lr": lr,
        "training.batch_size": bs,
        "model.hidden_size": hs
    }
    for lr, bs, hs in itertools.product(learning_rates, batch_sizes, hidden_sizes)
]

with open("grid.yaml", "w") as f:
    yaml.dump(grid, f)

print(f"Generated {len(grid)} experiments")  # 27 experiments
```

**Run grid:**
```bash
python generate_grid.py
python train.py \
  --config base.yml \
  --sweep-file grid.yaml \
  --n_jobs 10
```

---

### Example 4: Multi-Stage Pipeline

**Stage 1: Preprocessing**

**preprocess_config.yml:**
```yaml
input_file: data/raw/data.csv
output_dir: data/processed_${vinc:}
feature_columns: ["age", "income", "education"]

_snapshot_:
  repos:
    main: "."
  data:
    input: data/raw/data.csv
```

**Run preprocessing:**
```bash
python preprocess.py --config preprocess_config.yml
# Creates: data/processed_0001/
```

**Stage 2: Training**

**train_config.yml:**
```yaml
# Reference preprocessing stage
preprocessing: ${stage:${latest:data/processed_*}}

# Use preprocessing outputs
input_data: ${preprocessing.config.output_dir}/features.csv
feature_columns: ${preprocessing.config.feature_columns}

# Training config
model:
  type: mlp
  input_dim: 3  # matches len(feature_columns)

training:
  lr: 0.01
  epochs: 100

save_dir: results/train_${vinc:}

_snapshot_:
  repos:
    main: "."
  data:
    input: ${preprocessing.config.output_dir}/features.csv
  prevs:
    - ${latest:data/processed_*}
```

**Run training:**
```bash
python train.py --config train_config.yml
```

**Pipeline benefits:**
- Automatic lineage tracking via `${stage:}` resolver
- Input data validated via hashes
- Full reproducibility of entire pipeline

---

## Comparison with @flexcli

Understanding when to use each approach:

| Feature | @flexcli | FlexLockRunner |
|---------|----------|----------------|
| **Ease of Use** | ⭐⭐⭐ Simple decorator | ⭐⭐ More setup required |
| **Config from file** | ✅ `--config` | ✅ `--config` |
| **Overrides** | ✅ `-o` flag | ✅ `-o` + two-stage overrides |
| **Python defaults** | ✅ Via `default_config` param | ✅ Via `--defaults` flag |
| **Node selection** | ✅ `--experiment` | ✅ `--select` (more flexible) |
| **Sweep from file** | ✅ `--tasks` (simple) | ✅ `--sweep-file` (powerful) |
| **Sweep from config** | ❌ | ✅ `--sweep-key` |
| **Sweep from CLI** | ❌ | ✅ `--sweep` |
| **Declarative snapshots** | ❌ | ✅ `_snapshot_` section |
| **Check if exists** | ❌ | ✅ `--check-exists` |
| **Two-stage overrides** | ❌ | ✅ Pre/post select |
| **Parallel execution** | ✅ `--n_jobs` | ✅ `--n_jobs` |
| **Backend support** | ✅ Slurm, PBS | ✅ Slurm, PBS |

### When to Use @flexcli

```python
@flexcli
def main(cfg):
    train(cfg)
```

**Best for:**
- Getting started quickly
- Simple experiments
- Single config file workflows
- Scripts for other users (simpler interface)

### When to Use FlexLockRunner

```python
runner = FlexLockRunner()
runner.run()
```

**Best for:**
- Complex sweeps (grids, multi-parameter)
- Multi-stage pipelines
- Advanced configuration management
- Production workflows
- Power users who need full control

### Migration Path

Start with `@flexcli`, migrate to FlexLockRunner as needs grow:

**Phase 1: Simple script**
```python
@flexcli
def main(cfg):
    train(cfg)
```

**Phase 2: Need sweeps**
```python
# Switch to FlexLockRunner for better sweep support
runner = FlexLockRunner()
runner.run()
```

**Phase 3: Complex workflows**
```python
# Use declarative snapshots, check-exists, etc.
runner = FlexLockRunner()
runner.run()
```

---

## Best Practices

### 1. Use Declarative Snapshots

Keep snapshot config in YAML:

```yaml
# Good: Declarative
_snapshot_:
  repos: {main: "."}
  data: {train: "data/train.csv"}
```

```python
# Good: Clean code
def train(cfg):
    snapshot(cfg)  # Uses _snapshot_ from config
```

### 2. Organize Sweep Configs

**For small sweeps:** Use `--sweep` CLI flag

```bash
python train.py --sweep "0.001,0.01,0.1" --sweep-target lr --n_jobs 3
```

**For medium sweeps:** Use YAML files

```yaml
# sweep.yaml
- lr: 0.001
- lr: 0.01
- lr: 0.1
```

**For large sweeps:** Generate programmatically

```python
# generate_grid.py
grid = [{"lr": lr} for lr in [0.001, 0.01, 0.1, ...]]
```

### 3. Use Check-Exists for Long Sweeps

Always use `--check-exists` for sweeps that might be interrupted:

```bash
python train.py --sweep-file large_sweep.yaml --n_jobs 20 --check-exists
```

If interrupted, just rerun the same command - completed tasks are skipped.

### 4. Leverage Resolvers

Use resolvers for dynamic configs:

```yaml
save_dir: results/${now:%Y%m%d}/run${vinc:}
input: ${latest:data/preprocess_*/output.csv}
```

See [Resolvers documentation](./experimental.md) for more.

### 5. Organize Experiment Configs

Structure configs hierarchically:

```yaml
# experiments.yml
base:
  model: {type: mlp}
  training: {epochs: 100}

experiments:
  baseline:
    training: {lr: 0.001}
    save_dir: results/baseline

  large_lr:
    training: {lr: 0.1}
    save_dir: results/large_lr
```

Select experiments:
```bash
python train.py --config experiments.yml --select experiments.baseline
python train.py --config experiments.yml --select experiments.large_lr
```

---

## Summary

FlexLockRunner provides powerful features for advanced experiment management:

**Configuration:**
- Four-layer config system (defaults → file → select → overrides)
- Python module defaults
- Two-stage overrides (pre/post select)

**Sweeps:**
- Three sweep sources (config key, file, CLI)
- Sweep target injection
- Type inference for CLI sweeps

**Reproducibility:**
- Declarative snapshot tracking (`_snapshot_`)
- Check-exists for skipping completed runs
- Full lineage tracking

**When to use:**
- Complex sweeps and grids
- Multi-stage pipelines
- Advanced configuration needs
- Production workflows

**Next steps:**
- See [flexcli documentation](./flexcli.md) for the simpler decorator interface
- See [Resolvers documentation](./experimental.md) for dynamic configurations
- See [Parallel execution](./parallel.md) for distributed computing

FlexLockRunner gives you full control over experiment execution while maintaining FlexLock's reproducibility guarantees.
