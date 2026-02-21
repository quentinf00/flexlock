# Python API Reference

Comprehensive guide to FlexLock's Python API for programmatic experiment orchestration.

## Core Components

### `py2cfg`: Python to Configuration

Convert Python functions and classes into configuration dictionaries.

#### Basic Usage

```python
from flexlock import py2cfg

def train(lr=0.01, epochs=10, model=None):
    """Train a model."""
    pass

# Convert function to config
cfg = py2cfg(train)
# Result: {'_target_': 'module.train', 'lr': 0.01, 'epochs': 10}
```

#### With Overrides

```python
# Override default values
cfg = py2cfg(train, lr=0.1, epochs=100)
# Result: {'_target_': 'module.train', 'lr': 0.1, 'epochs': 100}
```

#### Nested Configurations

```python
class Transformer:
    def __init__(self, layers=6, heads=8):
        self.layers = layers
        self.heads = heads

# Nested py2cfg
cfg = py2cfg(
    train,
    lr=0.001,
    model=py2cfg(Transformer, layers=12, heads=16)
)

# Result:
# {
#   '_target_': 'module.train',
#   'lr': 0.001,
#   'epochs': 10,
#   'model': {
#     '_target_': 'module.Transformer',
#     'layers': 12,
#     'heads': 16
#   }
# }
```

#### Positional Arguments

```python
# For functions requiring positional args
cfg = py2cfg(train, model_name, lr=0.01)
# Result: {'_target_': 'module.train', '_args_': ['model_name'], 'lr': 0.01}
```

#### Partial Functions

```python
from functools import partial

# Create partial function
train_adam = partial(train, optimizer='adam')

cfg = py2cfg(train_adam, lr=0.01)
# Result: {'_target_': 'module.train', '_partial_': true, 'optimizer': 'adam', 'lr': 0.01}
```

---

### `instantiate`: Execute Configurations

Execute a configuration dictionary by instantiating the target.

```python
from flexlock.utils import instantiate

cfg = {
    '_target_': 'myproject.train.train',
    'lr': 0.01,
    'epochs': 100
}

# Execute
result = instantiate(cfg)
```

**Behavior:**
- Imports the module and function specified in `_target_`
- Passes config parameters as keyword arguments
- Handles `_args_` for positional arguments
- Supports `_partial_` for partial instantiation

---

### `@flexcli`: Command-Line Decorator

Transform a Python function into a CLI-enabled experiment.

#### Basic Usage

```python
from flexlock import flexcli

@flexcli
def train(lr=0.01, epochs=10, save_dir=None):
    """Train a model."""
    print(f"Training with lr={lr}, epochs={epochs}")
    print(f"Saving to {save_dir}")
    return {"accuracy": 0.95}

if __name__ == "__main__":
    train()  # CLI mode: parses sys.argv
```

**CLI usage:**
```bash
python train.py                       # Uses defaults
python train.py -o lr=0.1 epochs=20   # Override params
```

#### With Defaults

```python
@flexcli(lr=0.001, epochs=100)
def train(lr=0.01, epochs=10):
    pass

# Decorator defaults override function defaults
```

#### With Snapshot Configuration

```python
@flexcli(
    snapshot_config=dict(
        repos={
            'main': '.',                          # string shorthand for path
            'mylib': {'path': 'libs/mylib'},      # explicit dict form
        },
        data={'input': '${...input_path}'}
    )
)
def train(input_path, lr=0.01, save_dir=None):
    pass
```

**Enables:**
- Git repository tracking
- Data file hashing
- Reproducibility snapshots

> **Note:** When the config has a `_target_` key, FlexLock automatically tracks the git repository of the target function's source file — no explicit `repos` entry is needed in that case.

#### Debug Mode

```python
@flexcli(debug=True)  # or set FLEXLOCK_DEBUG=1
def train(lr=0.01):
    if lr == 0:
        raise ValueError("Invalid lr")

# On error: Drops into interactive debugger
```

---

## Project API

The `Project` class provides high-level orchestration for multi-stage experiments.

### Creating a Project

```python
from flexlock import Project

# Load from Python module
proj = Project(defaults='myproject.config.defaults')
```

**Python module structure:**
```python
# myproject/config/defaults.py
from flexlock import py2cfg

def preprocess(input_dir, output_dir):
    pass

def train(data_dir, lr=0.01, save_dir=None):
    pass

defaults = dict(
    preprocess=py2cfg(preprocess, input_dir='data/', output_dir='processed/'),
    train=py2cfg(train, data_dir='processed/', lr=0.01)
)
```

---

### `proj.get(key)`: Retrieve Configuration

Get a configuration node from the defaults.

```python
# Get config by key
train_cfg = proj.get('train')

# Modify before execution
train_cfg.lr = 0.1
train_cfg.batch_size = 64
```

**Returns:** `DictConfig` (OmegaConf)

---

### `proj.submit()`: Execute Configuration

Execute a configuration, with smart caching and HPC support.

#### Signature

```python
def submit(
    config: DictConfig,
    sweep: List[Dict] = None,
    n_jobs: int = 1,
    smart_run: bool = True,
    search_dirs: List[str] = None,
    wait: bool = True,
    pbs_config: str = None,
    slurm_config: str = None,
    sweep_dir_suffix: bool = False,
    match_include: List[str] = None,
    match_exclude: List[str] = None,
) -> ExecutionResult | List[ExecutionResult]
```

**Parameters:**
- `sweep_dir_suffix`: When `True`, appends `_sweep_{i:04d}` to each sweep run's `save_dir`. Default `False` (all sweep runs share the base `save_dir`).
- `match_include`: Override the git path include-patterns used during `smart_run` comparison (takes priority over per-repo patterns stored in `run.lock`).
- `match_exclude`: Override the git path exclude-patterns used during `smart_run` comparison.

#### Basic Execution

```python
# Get config and execute
cfg = proj.get('train')
result = proj.submit(cfg)

# Access results
print(result.save_dir)      # Where results are saved
print(result.status)        # "SUCCESS", "CACHED", "FAILED"
print(result.result)        # Return value from function
print(result['accuracy'])   # Dict-like access (if result is dict)
```

#### Smart Run (Caching)

```python
# First run: executes
result = proj.submit(cfg, smart_run=True)  # Runs

# Second run: cache hit
result = proj.submit(cfg, smart_run=True)  # ⚡ Skipped! Returns cached result
```

**How it works:**
- Generates fingerprint (code + data + config)
- Searches `search_dirs` for matching `run.lock`
- Returns cached result if found

**Custom search:**
```python
result = proj.submit(
    cfg,
    smart_run=True,
    search_dirs=['outputs/train/', 'archive/old_runs/']
)
```

#### Parameter Sweep

```python
# Define sweep
sweep = [
    dict(lr=0.001, batch_size=32),
    dict(lr=0.01, batch_size=64),
    dict(lr=0.1, batch_size=128),
]

# Execute sweep
results = proj.submit(cfg, sweep=sweep, n_jobs=3)

# Process results
for i, result in enumerate(results):
    print(f"Run {i}: accuracy={result['accuracy']}")

best = max(results, key=lambda r: r['accuracy'])
print(f"Best config: {best.cfg}")
```

#### HPC Execution (Slurm)

```python
result = proj.submit(
    cfg,
    slurm_config='slurm.yaml',
    wait=True  # Block until completion
)
```

**Slurm config:**
```yaml
startup_lines:
  - "#SBATCH --job-name=train"
  - "#SBATCH --cpus-per-task=8"
  - "#SBATCH --mem=32G"
  - "#SBATCH --time=04:00:00"
  - "module load cuda/11.8"
python_exe: "python"
```

#### HPC Execution (PBS)

```python
result = proj.submit(
    cfg,
    pbs_config='pbs.yaml',
    wait=False  # Submit and return immediately
)

# Check result later
# (Requires manual polling or separate script)
```

#### Async Execution

```python
# Submit without waiting
result = proj.submit(cfg, slurm_config='slurm.yaml', wait=False)
print(result.status)  # "SUBMITTED"

# Continue with other work...
```

---

### `proj.exists()`: Check for Cached Run

Check if a run with matching configuration exists.

```python
cfg = proj.get('train')

if proj.exists(cfg, search_dirs=['outputs/train/']):
    print("Run already exists, using cache")
    result = proj.get_result(cfg)
else:
    print("No cache found, executing")
    result = proj.submit(cfg)
```

---

### `proj.get_result()`: Load Cached Results

Load results from a previously completed run.

```python
cfg = proj.get('train')

# Load cached result (raises ValueError if not found)
result = proj.get_result(cfg, search_dirs=['outputs/'])

print(result.save_dir)
print(result.result)
```

**Result loading:**
- Tries `results.json` first
- Falls back to `run.lock` if available
- Returns `ExecutionResult` with `status="CACHED"`

---

## ExecutionResult

Object returned by `proj.submit()`.

### Attributes

```python
result = proj.submit(cfg)

result.save_dir   # str: Directory where results are saved
result.status     # str: "SUCCESS", "CACHED", "SKIPPED", "FAILED"
result.result     # Any: Return value from function
result.cfg        # DictConfig: Configuration used
```

### Dict-like Access

If the function returns a dict, access keys as attributes:

```python
def train(...):
    return {"accuracy": 0.95, "loss": 0.05}

result = proj.submit(cfg)
print(result.accuracy)      # 0.95
print(result['loss'])       # 0.05
print(result.get('f1', 0))  # 0 (default)
```

---

## Advanced Usage

### Multi-Stage Pipelines

```python
from pathlib import Path
from flexlock import Project, py2cfg

# Define pipeline
proj = Project(defaults='pipeline.defaults')

# Stage 1: Preprocess
preprocess_cfg = proj.get('preprocess')
preprocess_result = proj.submit(preprocess_cfg)

# Stage 2: Train (depends on Stage 1)
train_cfg = proj.get('train')
train_cfg.data_dir = preprocess_result.save_dir  # Use output from Stage 1
train_result = proj.submit(train_cfg)

# Stage 3: Evaluate (depends on Stage 2)
eval_cfg = proj.get('evaluate')
eval_cfg.model_path = Path(train_result.save_dir) / 'model.pth'
eval_result = proj.submit(eval_cfg)

print(f"Final accuracy: {eval_result['accuracy']}")
```

**With smart run:**
```python
# Re-run entire pipeline
# Unchanged stages are automatically skipped
preprocess_result = proj.submit(preprocess_cfg)  # ⚡ Cached
train_result = proj.submit(train_cfg)            # ⚡ Cached
eval_result = proj.submit(eval_cfg)              # ⚡ Cached
```

---

### Sweep with Early Stopping

```python
sweep = [dict(lr=v) for v in [0.001, 0.01, 0.1, 1.0]]

results = []
for i, override in enumerate(sweep):
    cfg = proj.get('train')
    cfg.merge_with(override)

    result = proj.submit(cfg, smart_run=False)
    results.append(result)

    # Early stop if accuracy > 0.95
    if result['accuracy'] > 0.95:
        print(f"Found good config at iteration {i}")
        break

best = max(results, key=lambda r: r['accuracy'])
```

---

### Dynamic Configuration

```python
from datetime import datetime

cfg = proj.get('train')

# Dynamic save_dir with timestamp
cfg.save_dir = f"outputs/train_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Dynamic data path
cfg.data_dir = "data/latest" if use_latest else "data/stable"

result = proj.submit(cfg)
```

---

### Conditional Execution

```python
cfg = proj.get('train')

# Only run if not cached
if not proj.exists(cfg):
    print("Training model...")
    result = proj.submit(cfg, smart_run=False)
else:
    print("Using cached model")
    result = proj.get_result(cfg)

# Use result
model_path = Path(result.save_dir) / 'model.pth'
```

---

## Best Practices

### 1. Always Use `save_dir`

```python
# Bad: No save_dir
cfg = py2cfg(train, lr=0.01)

# Good: Explicit save_dir
cfg = py2cfg(train, lr=0.01, save_dir='outputs/train_baseline')
```

### 2. Use Smart Run by Default

```python
# Let FlexLock handle caching
result = proj.submit(cfg, smart_run=True)

# Only disable for debugging
result = proj.submit(cfg, smart_run=False)
```

### 3. Structure Configs Hierarchically

```python
# Good: Nested structure
defaults = dict(
    base_dir='outputs/',
    preprocess=py2cfg(preprocess, save_dir='${base_dir}/preprocess'),
    train=py2cfg(train, save_dir='${base_dir}/train')
)

# Access root variables via interpolation
# OmegaConf resolves ${base_dir} at runtime
```

### 4. Track Data Dependencies

```python
cfg = py2cfg(
    train,
    input_data='data/train.csv',
    save_dir='outputs/train',
    snapshot_config=dict(
        repos={'main': '.'},          # string shorthand
        data={'train_data': '${...input_data}'}
    )
)

# Now FlexLock tracks:
# - Code version (git tree hash)
# - Data version (file hash)
# - Configuration
```

To track only specific files within a repo (speeds up `smart_run` by ignoring irrelevant changes):

```python
snapshot_config=dict(
    repos={
        'main': {
            'path': '.',
            'include': ['src/mymodule/**'],   # only these paths matter
            'exclude': ['tests/**'],           # ignore tests
        }
    }
)
```

Or resolve the repo path automatically from a Python module name:

```python
snapshot_config=dict(
    repos={
        'mylib': {'module': 'mylib'}   # path resolved via importlib
    }
)
```

### 5. Use Sweeps for Exploration

```python
# Define parameter grid
param_grid = [
    dict(lr=lr, batch_size=bs)
    for lr in [0.001, 0.01, 0.1]
    for bs in [32, 64, 128]
]

# Execute in parallel
results = proj.submit(
    cfg,
    sweep=param_grid,
    n_jobs=8,
    smart_run=True  # Skip already-run configs
)

# Analyze results
best = max(results, key=lambda r: r.get('accuracy', 0))
```

---

## See Also

- [CLI Reference](./cli_reference.md) - Command-line usage
- [HPC Integration](./hpc_integration.md) - Slurm/PBS configuration
- [Debugging](./debugging.md) - Interactive debugging
- [Reference](./reference.md) - Environment variables and exceptions
