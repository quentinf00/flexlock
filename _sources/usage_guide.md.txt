# Complete Usage Guide

Comprehensive guide covering all FlexLock features and use cases.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Configuration Methods](#configuration-methods)
3. [Execution Modes](#execution-modes)
4. [Reproducibility](#reproducibility)
5. [Parameter Sweeps](#parameter-sweeps)
6. [HPC Integration](#hpc-integration)
7. [Pipelines](#pipelines)
8. [Smart Caching](#smart-caching)
9. [Common Patterns](#common-patterns)

---

## Getting Started

### Installation

```bash
pip install flexlock
```

### Your First Experiment

```python
# train.py
from flexlock import flexcli

@flexcli
def train(lr=0.01, epochs=10, save_dir=None):
    """Train a model."""
    print(f"Training: lr={lr}, epochs={epochs}")
    return {"accuracy": 0.95, "loss": 0.05}

if __name__ == "__main__":
    train()
```

**Run it:**
```bash
python train.py                    # Use defaults
python train.py -o lr=0.1          # Override learning rate
python train.py --debug            # Enable debug mode
```

---

## Configuration Methods

FlexLock supports three configuration methods:

### 1. Function Defaults (`@flexcli`)

Best for: Simple scripts, quick prototypes

```python
from flexlock import flexcli

@flexcli
def run(param1=10, param2="default"):
    print(f"{param1}, {param2}")

if __name__ == "__main__":
    run()
```

**CLI:**
```bash
python script.py -o param1=20 param2=custom
```

---

### 2. Python Configs (`py2cfg`)

Best for: Complex configurations, nested objects, type safety

```python
# config.py
from flexlock import py2cfg

class Model:
    def __init__(self, layers=6, dropout=0.1):
        pass

def train(model, lr=0.01, save_dir=None):
    pass

# Create configs
defaults = dict(
    base_dir='outputs/',
    train=py2cfg(
        train,
        model=py2cfg(Model, layers=12, dropout=0.2),
        lr=0.001,
        save_dir='${base_dir}/train'
    )
)
```

**CLI:**
```bash
flexlock-run -d config.defaults -s train
flexlock-run -d config.defaults -s train -O lr=0.01
```

**Python:**
```python
from flexlock import Project

proj = Project(defaults='config.defaults')
result = proj.submit(proj.get('train'))
```

---

### 3. YAML Configs

Best for: Declarative configs, sharing with non-Python users

```yaml
# config.yaml
_target_: myproject.train.train

model:
  _target_: myproject.models.Transformer
  layers: 12
  dropout: 0.2

lr: 0.001
epochs: 100
save_dir: outputs/train
```

**CLI:**
```bash
flexlock-run -c config.yaml
flexlock-run -c config.yaml -o lr=0.01
```

---

## Execution Modes

### 1. Direct Python Execution

```python
from flexlock import flexcli

@flexcli
def train(lr=0.01):
    return {"accuracy": 0.95}

# Direct call (Python API)
result = train(lr=0.1)  # Returns dict

# CLI mode
if __name__ == "__main__":
    train()  # Parses sys.argv
```

---

### 2. CLI with `flexlock-run`

```bash
# From Python config
flexlock-run -d myproject.config -s train

# From YAML config
flexlock-run -c config.yaml

# With overrides
flexlock-run -d config -s train -O lr=0.1
```

---

### 3. Python Project API

```python
from flexlock import Project

proj = Project(defaults='myproject.config')

# Get and execute
cfg = proj.get('train')
result = proj.submit(cfg)

# Access results
print(result.save_dir)
print(result['accuracy'])
```

---

## Reproducibility

FlexLock tracks code, data, and configuration for every run.

### Enable Tracking

**With decorator:**
```python
@flexcli(
    snapshot_config=dict(
        repos={'main': '.'},           # Track git repo
        data={'input': '${...input_path}'}  # Track data files
    )
)
def train(input_path, save_dir=None):
    pass
```

**With py2cfg:**
```python
cfg = py2cfg(
    train,
    input_path='data/train.csv',
    save_dir='outputs/train',
    snapshot_config=dict(
        repos={'main': '.', 'submodule': 'libs/mylib'},
        data={'train_data': '${...input_path}'}
    )
)
```

---

### Snapshot Contents

Every run creates `run.lock`:

```yaml
# outputs/train/run_0001/run.lock
timestamp: "2024-01-15T14:30:00.123456"

repos:
  main:
    commit: "abc123..."     # Git commit hash
    tree: "def456..."       # Git tree hash (key for equality)
    is_dirty: false

data:
  train_data: "xxh64_789xyz..."  # Data file hash

config:
  lr: 0.01
  epochs: 100
  input_path: "data/train.csv"
  save_dir: "outputs/train/run_0001"
```

---

### Compare Runs

```bash
flexlock-diff outputs/train/run_0001 outputs/train/run_0002
```

**Output:**
```
Differences:
  config.lr: 0.01 → 0.1
  data.train_data: hash_abc → hash_xyz
```

---

## Parameter Sweeps

Run multiple experiments with different parameters.

### CLI Sweeps

**Comma-separated values:**
```bash
flexlock-run -d config -s train \
  --sweep "0.001,0.01,0.1" \
  --sweep-target lr \
  --n_jobs 3
```

**From file:**
```bash
# sweep.yaml
- {lr: 0.001, batch_size: 32}
- {lr: 0.01, batch_size: 64}
- {lr: 0.1, batch_size: 128}
```

```bash
flexlock-run -d config -s train \
  --sweep-file sweep.yaml \
  --n_jobs 3
```

**From config:**
```python
# config.py
defaults = dict(
    train=py2cfg(train),
    param_grid=[
        dict(lr=0.001, batch_size=32),
        dict(lr=0.01, batch_size=64),
    ]
)
```

```bash
flexlock-run -d config --sweep-key param_grid --n_jobs 2
```

---

### Python API Sweeps

```python
proj = Project(defaults='config.defaults')

# Define sweep
sweep = [
    dict(lr=0.001, batch_size=32),
    dict(lr=0.01, batch_size=64),
    dict(lr=0.1, batch_size=128),
]

# Execute
results = proj.submit(
    proj.get('train'),
    sweep=sweep,
    n_jobs=3
)

# Process results
for i, result in enumerate(results):
    print(f"Run {i}: accuracy={result['accuracy']:.3f}")

best = max(results, key=lambda r: r['accuracy'])
print(f"Best LR: {best.cfg.lr}")
```

---

## HPC Integration

Execute experiments on HPC clusters using Slurm or PBS.

### Slurm Configuration

**slurm.yaml:**
```yaml
startup_lines:
  - "#SBATCH --job-name=flexlock"
  - "#SBATCH --cpus-per-task=8"
  - "#SBATCH --mem=32G"
  - "#SBATCH --time=04:00:00"
  - "#SBATCH --gres=gpu:1"
  - "#SBATCH --array=0-99"    # 100 workers
  - "module load cuda/11.8"
  - "source activate myenv"

python_exe: "python"
```

**CLI:**
```bash
flexlock-run -d config -s train \
  --sweep-file sweep.yaml \
  --slurm-config slurm.yaml
```

**Python:**
```python
results = proj.submit(
    cfg,
    sweep=sweep,
    slurm_config='slurm.yaml',
    wait=True  # Block until completion
)
```

---

### PBS Configuration

**pbs.yaml:**
```yaml
startup_lines:
  - "#PBS -l select=1:ncpus=8:mem=32gb"
  - "#PBS -l walltime=04:00:00"
  - "#PBS -N flexlock"
  - "#PBS -J 0-99"  # 100 workers
  - "cd $PBS_O_WORKDIR"
  - "conda activate myenv"

python_exe: "python"
```

**CLI:**
```bash
flexlock-run -d config -s train \
  --sweep-file sweep.yaml \
  --pbs-config pbs.yaml
```

---

### Containerized Execution

**Singularity:**
```yaml
# pbs_singularity.yaml
startup_lines:
  - "#PBS -l select=1:ncpus=4"
  - "cd $PBS_O_WORKDIR"

python_exe: |
  singularity run
  --bind $(pwd)/src:/app/src
  --bind $(pwd)/outputs:/workspace/outputs
  --pwd /workspace
  myenv.sif python
```

**Docker:**
```yaml
startup_lines:
  - "cd $WORKSPACE"

python_exe: |
  docker run
  -v $(pwd):/workspace
  -w /workspace
  myimage:latest python
```

---

## Pipelines

Chain multiple stages with dependency tracking.

### Basic Pipeline

```python
from flexlock import Project, py2cfg

# Define stages
def preprocess(input_dir, save_dir):
    # ... processing ...
    return {"output_path": f"{save_dir}/processed.csv"}

def train(data_path, lr, save_dir):
    # ... training ...
    return {"accuracy": 0.95}

def evaluate(model_dir, save_dir):
    # ... evaluation ...
    return {"final_accuracy": 0.96}

# Create project
proj = Project(defaults='pipeline.defaults')

# Execute pipeline
prep_result = proj.submit(proj.get('preprocess'))

train_cfg = proj.get('train')
train_cfg.data_path = prep_result['output_path']
train_result = proj.submit(train_cfg)

eval_cfg = proj.get('evaluate')
eval_cfg.model_dir = train_result.save_dir
eval_result = proj.submit(eval_cfg)

print(f"Final: {eval_result['final_accuracy']}")
```

---

### Pipeline with Config Links

```python
# pipeline.py
from flexlock import py2cfg

defaults = dict(
    base_dir='outputs/pipeline',

    preprocess=py2cfg(
        preprocess,
        input_dir='data/raw',
        save_dir='${base_dir}/preprocess'
    ),

    train=py2cfg(
        train,
        data_path='${latest:${base_dir}/preprocess/*/processed.csv}',
        lr=0.01,
        save_dir='${base_dir}/train'
    ),

    evaluate=py2cfg(
        evaluate,
        model_dir='${latest:${base_dir}/train/*/}',
        save_dir='${base_dir}/evaluate'
    )
)
```

**Execute:**
```python
proj = Project(defaults='pipeline.defaults')

# All dependencies resolved automatically
for stage in ['preprocess', 'train', 'evaluate']:
    result = proj.submit(proj.get(stage))
    print(f"{stage}: {result.status}")
```

---

### Pipeline with Smart Run

```python
# First execution
proj = Project(defaults='pipeline.defaults')

prep_result = proj.submit(proj.get('preprocess'))     # Runs
train_result = proj.submit(proj.get('train'))         # Runs
eval_result = proj.submit(proj.get('evaluate'))       # Runs

# Rerun (no changes)
prep_result = proj.submit(proj.get('preprocess'))     # ⚡ Cached
train_result = proj.submit(proj.get('train'))         # ⚡ Cached
eval_result = proj.submit(proj.get('evaluate'))       # ⚡ Cached

# Modify preprocess, rerun
prep_cfg = proj.get('preprocess')
prep_cfg.some_param = 'new_value'

prep_result = proj.submit(prep_cfg, smart_run=False)  # Runs (forced)
train_result = proj.submit(proj.get('train'))         # Runs (deps changed)
eval_result = proj.submit(proj.get('evaluate'))       # Runs (deps changed)
```

---

## Smart Caching

FlexLock automatically caches and reuses results.

### How It Works

1. **Fingerprint Generation:** Combines code (git tree hash) + data (file hashes) + config
2. **Search:** Looks for matching `run.lock` files in `search_dirs`
3. **Match:** Compares fingerprints using `RunDiff`
4. **Cache Hit:** Returns existing result without rerunning

---

### Enable Smart Run

**Default (enabled):**
```python
result = proj.submit(cfg)  # smart_run=True by default
```

**Explicit:**
```python
result = proj.submit(cfg, smart_run=True, search_dirs=['outputs/train/'])
```

**Disable:**
```python
result = proj.submit(cfg, smart_run=False)  # Always runs
```

---

### Custom Search Directories

```python
result = proj.submit(
    cfg,
    smart_run=True,
    search_dirs=[
        'outputs/train/',
        'archive/previous_runs/',
        '/shared/team_results/'
    ]
)
```

---

### Check Before Running

```python
cfg = proj.get('train')

if proj.exists(cfg, search_dirs=['outputs/train/']):
    print("Using cached result")
    result = proj.get_result(cfg)
else:
    print("Running new experiment")
    result = proj.submit(cfg)
```

---

## Common Patterns

### Pattern 1: Hyperparameter Search

```python
from flexlock import Project

proj = Project(defaults='config.defaults')

# Grid search
lr_values = [0.0001, 0.001, 0.01, 0.1]
bs_values = [16, 32, 64, 128]

sweep = [
    dict(lr=lr, batch_size=bs)
    for lr in lr_values
    for bs in bs_values
]

results = proj.submit(
    proj.get('train'),
    sweep=sweep,
    n_jobs=8,
    smart_run=True  # Skip already-run configs
)

# Find best
best = max(results, key=lambda r: r.get('accuracy', 0))
print(f"Best config: lr={best.cfg.lr}, bs={best.cfg.batch_size}")
print(f"Best accuracy: {best.accuracy:.4f}")
```

---

### Pattern 2: Iterative Refinement

```python
# Start with baseline
cfg = proj.get('train')
cfg.lr = 0.01
baseline = proj.submit(cfg)

print(f"Baseline: {baseline.accuracy:.4f}")

# Try improvements
for lr in [0.005, 0.001, 0.0005]:
    cfg.lr = lr
    result = proj.submit(cfg)

    print(f"LR={lr}: {result.accuracy:.4f}")

    if result.accuracy > baseline.accuracy + 0.01:
        print(f"Improvement found! New baseline.")
        baseline = result
```

---

### Pattern 3: Multi-Stage with Sweeps

```python
# Stage 1: Preprocess (once)
prep_cfg = proj.get('preprocess')
prep_result = proj.submit(prep_cfg)

# Stage 2: Train (sweep)
train_cfg = proj.get('train')
train_cfg.data_path = prep_result['output_path']

train_sweep = [dict(lr=lr) for lr in [0.001, 0.01, 0.1]]
train_results = proj.submit(train_cfg, sweep=train_sweep, n_jobs=3)

# Stage 3: Evaluate best model
best_train = max(train_results, key=lambda r: r['val_accuracy'])

eval_cfg = proj.get('evaluate')
eval_cfg.model_path = best_train.save_dir + '/model.pth'
eval_result = proj.submit(eval_cfg)

print(f"Test accuracy: {eval_result['test_accuracy']:.4f}")
```

---

### Pattern 4: Resume Failed Sweep

```bash
# Initial sweep (some jobs fail)
flexlock-run -d config --sweep-file sweep.yaml --n_jobs 10

# Check status
flexlock-status outputs/sweep/run.lock.tasks.db

# Rerun (only failed tasks execute)
flexlock-run -d config --sweep-file sweep.yaml --n_jobs 10
```

---

### Pattern 5: Cross-Validation Pipeline

```python
from flexlock import Project, py2cfg

proj = Project(defaults='cv.defaults')

folds = 5
results = []

for fold in range(folds):
    # Train on fold
    train_cfg = proj.get('train')
    train_cfg.fold = fold
    train_cfg.save_dir = f'outputs/cv/fold_{fold}'

    train_result = proj.submit(train_cfg, smart_run=True)

    # Evaluate
    eval_cfg = proj.get('evaluate')
    eval_cfg.model_dir = train_result.save_dir
    eval_cfg.fold = fold

    eval_result = proj.submit(eval_cfg, smart_run=True)
    results.append(eval_result['accuracy'])

print(f"CV Accuracy: {sum(results)/len(results):.4f} ± {std(results):.4f}")
```

---

## Tips & Best Practices

### 1. Always Specify `save_dir`

```python
# Good
cfg = py2cfg(train, save_dir='outputs/train_baseline')

# Bad (will use default, may conflict)
cfg = py2cfg(train)
```

---

### 2. Use Resolvers for Dynamic Values

```python
# Auto-versioning
cfg = py2cfg(train, save_dir='${vinc:outputs/train/run}')

# Timestamps
cfg = py2cfg(train, save_dir='outputs/train_${now:%Y%m%d_%H%M%S}')

# Latest dependency
cfg = py2cfg(train, data_path='${latest:outputs/preprocess/*/data.csv}')
```

---

### 3. Track Data Dependencies

```python
cfg = py2cfg(
    train,
    input_data='data/train.csv',
    snapshot_config=dict(
        repos={'main': '.'},
        data={'train': '${...input_data}'}
    )
)
```

---

### 4. Use `smart_run` by Default

```python
# Let FlexLock skip redundant work
result = proj.submit(cfg, smart_run=True)

# Only disable for debugging
result = proj.submit(cfg, smart_run=False)
```

---

### 5. Structure Configs Hierarchically

```python
defaults = dict(
    base_dir='outputs/',
    shared_params=dict(lr=0.01, batch_size=32),

    train=py2cfg(
        train,
        **shared_params,
        save_dir='${base_dir}/train'
    ),

    finetune=py2cfg(
        finetune,
        **shared_params,
        lr=0.001,  # Override
        save_dir='${base_dir}/finetune'
    )
)
```

---

## Troubleshooting

### Issue: "Task DB locked"

**Cause:** Multiple processes accessing DB simultaneously

**Solution:**
- Use HPC backend (handles concurrency)
- Reduce `n_jobs` for local execution
- Check for stale DB locks

---

### Issue: Smart run not finding cached results

**Cause:** Config/code/data changed slightly

**Solution:**
```bash
# Check diff
flexlock-diff current_config existing_run/

# Common causes:
# - save_dir changed (use normalization)
# - Code changed (git tree hash different)
# - Data changed (file hash different)
```

---

### Issue: Sweep not using all workers

**Cause:** Fewer tasks than workers

**Solution:**
```bash
# 100 tasks, 10 workers = efficient
flexlock-run --sweep-file 100tasks.yaml --n_jobs 10

# 5 tasks, 10 workers = 5 workers idle
flexlock-run --sweep-file 5tasks.yaml --n_jobs 10
```

---

## Next Steps

- [CLI Reference](./cli_reference.md) - Complete CLI documentation
- [Python API](./python_api.md) - Programmatic usage
- [HPC Integration](./hpc_integration.md) - Slurm/PBS setup
- [Resolvers](./resolvers.md) - Dynamic configuration values
- [Debugging](./debugging.md) - Interactive debugging features

---

For more help:
- [GitHub Issues](https://github.com/quentinf00/flexlock/issues)
- [Documentation](https://quentinf00.github.io/flexlock/)
