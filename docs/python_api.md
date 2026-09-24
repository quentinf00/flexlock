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
# Result: {'_target_': 'module.train', 'lr': 0.01, 'epochs': 10, 'model': None}
```

Every parameter with a default is captured — including ones whose default
is ``None``. Override or remove them downstream if you don't want them in
the run lock.

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
    _snapshot_=dict(
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

Enable debug mode via the `--debug` CLI flag or the `FLEXLOCK_DEBUG=1` environment variable:

```bash
python train.py --debug
FLEXLOCK_DEBUG=1 python train.py
```

On error, FlexLock drops into an interactive debugger. See [Debugging](./debugging.md) for details.

---

## Project API

The `Project` class provides high-level orchestration for multi-stage experiments.

### Creating a Project

```python
from flexlock import Project

# Load defaults from a Python module
proj = Project(defaults='myproject.config.defaults')

# Or from a file path — bare path infers the `defaults` variable name
proj = Project(defaults='configs/defaults.py')
# Equivalent to: Project(defaults='configs/defaults.py:defaults')

# Or point at a differently-named variable
proj = Project(defaults='configs/experiments.py:hyperparam_grid')

# Or from a pre-built DictConfig / dict
proj = Project(defaults={'train': {'lr': 0.01}})

# Or with no defaults — useful for one-off submissions
proj = Project()
```

### One-off submission without a Project

For a single config that doesn't need pipeline plumbing:

```python
from flexlock import submit, py2cfg

cfg = py2cfg(train, lr=0.01, save_dir='outputs/train')
result = submit(cfg, slurm_config='configs/slurm_gpu.yaml')
```

`flexlock.submit` is a thin wrapper over `Project().submit` — all kwargs
(`sweep`, `smart_run`, `overrides`, `force`, etc.) are forwarded.

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

Get a configuration node from the defaults. The returned config is
**self-contained**: root-scope references (`${some_anchor}`) are frozen to
concrete values, while resolver calls (`${vinc:}`, `${latest:}`,
`${run_lock:}`) and intra-sub-tree references are preserved for resolution
at submit time.

When the project was built from an import string
(`Project("pkg.xps.pipeline_cfg")`) and the node is runnable (`_target_` +
`save_dir`), `get` also records the preset as `_preset_`
(`defaults: pkg.xps:pipeline_cfg`, `select: <key>`), so the run shows up in
`flexlock runs` / `flexlock presets`. It never affects caching.

```python
# Get config by key
train_cfg = proj.get('train')

# Modify before execution
train_cfg.lr = 0.1
train_cfg.batch_size = 64

# train_cfg can be pickled, merged, or shipped to an HPC worker
# without losing root context — every ${root_anchor} has already been
# substituted with its value at the moment of the get() call.
proj.submit(train_cfg, slurm_config='configs/slurm_gpu.yaml')
```

**Anchor-update workflow:** if you want a root-level anchor change to
propagate into a stage, update `proj.defaults` *before* calling `proj.get`:

```python
OmegaConf.update(proj.defaults, 'cnf_run_dir', result.save_dir)
eval_cfg = proj.get('cnf_eval_val')   # picks up the new anchor
```

A previously-fetched config will **not** see anchor updates retroactively —
its root refs are already frozen. Re-call `proj.get` to refresh.

**Returns:** `DictConfig` (OmegaConf)

---

### `proj.submit()`: Execute Configuration

Execute a configuration, with smart caching and HPC support.

#### Signature

```python
def submit(
    config: DictConfig | str | None = None,
    sweep: List[Dict] = None,
    sweep_target: str = None,
    n_jobs: int = 1,
    smart_run: bool = True,
    search_dirs: List[str] = None,
    wait: bool = True,
    pbs_config: str = None,
    slurm_config: str = None,
    sweep_dir_suffix: bool = False,
    match_include: List[str] = None,
    match_exclude: List[str] = None,
    isolated: bool = False,
    force: bool = False,
    overrides: dict | List[str] = None,
    merge: str | Path | dict = None,
    debug: bool = False,
    print_config: bool = False,
) -> ExecutionResult | List[ExecutionResult] | None
```

**Parameters:**
- `config`: Accepts a `DictConfig`, a key string (looked up via `proj.get`), or `None` (use `proj.defaults`).
- `sweep_target`: Dot-path where each sweep item is merged into the base config. `None` merges items at the root.
- `overrides`: Dict (`{'lr': 0.01}`) or dotlist (`['lr=0.01']`) merged into `config` before execution.
- `merge`: Path to a YAML file (or a dict) merged into `config` before execution. `overrides` is applied after `merge`.
- `debug`: Wrap the user function with the post-mortem debugger so exceptions drop into PDB.
- `print_config`: Print the resolved config and return `None` without executing — useful for inspecting sweep-merged or override-merged configs before launching.
- `sweep_dir_suffix`: When `True`, nests each sweep run under `<save_dir>/sweep_{i:04d}/`. Default `False` (all sweep runs share the base `save_dir`).
- `match_include`: Override the git path include-patterns used during `smart_run` comparison (takes priority over per-repo patterns stored in `run.lock`).
- `match_exclude`: Override the git path exclude-patterns used during `smart_run` comparison.

#### CLI/Python parity

`flexlock-run` and `proj.submit()` share the same execution kernel. Equivalences:

| CLI flag                 | Python kwarg                              |
|--------------------------|-------------------------------------------|
| `-s <key>` (select)      | `submit('key', ...)` (str dispatches via `get`) |
| `-O key=val` / `-M file` (post-select) | `overrides={...}` / `merge=...`     |
| `--sweep-file path.yaml` | `sweep=load_sweep(sweep_file='path.yaml')` |
| `--sweep-target X`       | `sweep_target='X'`                        |
| `--debug`                | `debug=True`                              |
| `--print-config`         | `print_config=True`                       |

The `load_sweep` utility is also exported at the package level:

```python
from flexlock import load_sweep
sweep = load_sweep(sweep_file='configs/ablation.yaml')
proj.submit('train', sweep=sweep, sweep_target='lit_module',
            slurm_config='configs/slurm_gpu.yaml')
```

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
- Searches `search_dirs` for run directories containing **both** `run.lock`
  (written before execution) and `run.complete` (written after the user
  function returns successfully)
- Returns cached result on a match; runs that have only `run.lock` (previous
  attempts interrupted before completion) are skipped, not treated as cache
  hits

**Custom search:**
```python
result = proj.submit(
    cfg,
    smart_run=True,
    search_dirs=['outputs/train/', 'archive/old_runs/']
)
```

#### Cache markers and `force=True`

Each completed run leaves two files alongside its outputs:

- `run.lock` — config + provenance, written before execution starts.
- `run.complete` — JSON with completion timestamp, written after the user
  function returns. A cache hit requires both.

To force re-execution while keeping prior outputs in place:

```python
proj.submit(cfg, force=True)   # deletes run.complete, runs again into same dir
```

`force=True` does **not** delete `save_dir` or `run.lock` — only the
completion marker. The user function overwrites outputs in place.

**Migrating from older versions:** runs created before this scheme exists
have only `run.lock` and would be treated as incomplete. Backfill them once:

```bash
flexlock migrate-cache-markers outputs/
```

This writes `run.complete` for any dir that has `run.lock` plus at least one
non-hidden output file. To prune stale lock-only dirs instead:

```bash
flexlock gc --incomplete outputs/
```

#### Parameter Sweep

```python
# Define sweep
sweep = [
    dict(lr=0.001, batch_size=32),
    dict(lr=0.01, batch_size=64),
    dict(lr=0.1, batch_size=128),
]

if __name__ == "__main__":
    # n_jobs > 1 spawns multiprocessing workers (see "Parallelism" note
    # below) and therefore must be guarded by `if __name__ == "__main__":`
    # when the call is at module scope. Without the guard, importing the
    # script (which spawn does to bootstrap the children) re-runs the call
    # and the process never terminates.
    results = proj.submit(cfg, sweep=sweep, n_jobs=3)

    # Process results
    for i, result in enumerate(results):
        print(f"Run {i}: accuracy={result['accuracy']}")

    best = max(results, key=lambda r: r['accuracy'])
    print(f"Best config: {best.cfg}")
```

> **Parallelism note.** ``n_jobs > 1`` and ``isolated=True`` both use
> Python's ``multiprocessing`` with the ``spawn`` start method (chosen to
> avoid GPU/CUDA fork hazards). Spawn re-imports the launching script in
> each child, so any module-scope ``proj.submit(...)`` call **must** be
> placed under ``if __name__ == "__main__":``. Notebook and REPL contexts
> are fine. ``n_jobs=1`` without ``isolated=True`` runs in-process and
> does not need the guard.

**Per-item `save_dir` containment.** Each sweep item's `save_dir` must
nest under the sweep root (taken from the base config's `save_dir`, or
the first item's parent dir). The tasks DB and per-item lineage markers
all live in the sweep root tree. Violating containment raises a
`FlexLockValidationError` listing the offending items before any work is
queued.

**Tracking per-item `save_dir` in derived paths.** Use *intra-node*
references (relative to the same config node) rather than absolute root
references:

```python
# ✅ Tracks per-item save_dir overrides — recommended
cfg = py2cfg(train,
    save_dir='outputs/train',
    log_dir='${save_dir}/logs',           # intra-node ref
    ckpt_dir='${save_dir}/checkpoints',
)
proj.submit(cfg, sweep=[
    dict(save_dir='outputs/sweep/a'),     # log_dir becomes outputs/sweep/a/logs
    dict(save_dir='outputs/sweep/b'),
])

# ❌ Frozen at proj.get() time — won't track sweep overrides
cfg = py2cfg(train,
    save_dir='outputs/train',
    log_dir='${main.save_dir}/logs',      # cross-tree ref
)
```

Cross-tree refs (`${main.save_dir}`, `${root_anchor}`) are frozen to
concrete values at `proj.get()` so the sub-node remains self-contained
under pickling and merge. Intra-node refs (`${save_dir}`,
`${some_local_key}`) are preserved and re-resolve on each sweep item.

**Previewing a sweep.** Set `print_config=True` while passing `sweep=...`
to print each item's fully-merged config without executing:

```python
proj.submit(cfg, sweep=sweep, print_config=True)
# --- sweep item 0 ---
# lr: 0.001
# batch_size: 32
# ...
```

#### Post-sweep chaining

After a sweep, downstream stages typically need to run once per sweep
result, each anchored at the result's `save_dir`. `proj.submit_chained`
packages this loop:

```python
chained = proj.submit_chained(
    base_cfg,
    sweep=[{'fourier_sigma': s} for s in [1.0, 2.0, 5.0]],
    downstream=[
        # (stage_key, anchor_wiring)
        # anchor_wiring maps anchor name in proj.defaults → result attribute
        ('encode_val',   {'cnf_run_dir': 'save_dir'}),
        ('cnf_eval_val', {'cnf_run_dir': 'save_dir'}),
    ],
    sweep_kwargs={'slurm_config': 'configs/slurm_gpu.yaml', 'n_jobs': 3},
    downstream_kwargs={'slurm_config': 'configs/slurm_gpu.yaml'},
)

# Iterate (sweep_result, downstream_results) pairs:
for sweep_r, downstream_rs in chained:
    encode_r, eval_r = downstream_rs
    print(sweep_r.save_dir, eval_r['val_score'])
```

For each sweep item, the parent's `save_dir` is written into the named
anchor on `proj.defaults`, then each downstream stage is fetched via
`proj.get(key)` (so the new anchor propagates through interpolations)
and submitted. `downstream_kwargs` defaults to `smart_run=False` to
avoid stale-cache false hits between iterations — pass
`{'smart_run': True}` explicitly if you want caching.

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

### `proj.run_stage()`: Execute a Pipeline Stage

Convenience method that wraps `submit()` with automatic `search_dirs` discovery and `save_dir` propagation — the two things you'd otherwise have to do manually in every pipeline.

#### Signature

```python
def run_stage(
    cfg: DictConfig,
    stage_name: str = None,
    smart_run: bool = True,
    search_dirs: List[str] = None,
    **submit_kwargs,
) -> ExecutionResult
```

**Parameters:**
- `cfg`: Stage configuration (DictConfig)
- `stage_name`: Name of the stage. If `None`, inferred from `cfg.save_dir` (last path component).
- `smart_run`: Whether to check for cached runs (default `True`)
- `search_dirs`: Directories to search for cached runs. If `None`, auto-discovered by scanning sibling experiment directories with the same stage name.
- `**submit_kwargs`: Additional arguments forwarded to `submit()` (e.g., `isolated=True`)

#### Basic Usage

```python
proj = Project(defaults='pipeline.defaults')
cfg = proj.get('train')
cfg.save_dir = 'results/exp_001/train'

# Executes the stage, auto-discovers search_dirs, propagates save_dir
result = proj.run_stage(cfg)

# cfg.save_dir is now updated to result.save_dir (useful for downstream stages)
print(cfg.save_dir)  # results/exp_001/train
```

#### Multi-Stage Pipeline

```python
proj = Project(defaults='pipeline.defaults')

# Stage 1
prep_cfg = proj.get('preprocess')
prep_cfg.save_dir = 'results/exp_001/preprocess'
proj.run_stage(prep_cfg)

# Stage 2 — uses prep_cfg.save_dir (propagated by run_stage)
train_cfg = proj.get('train')
train_cfg.data_dir = prep_cfg.save_dir
train_cfg.save_dir = 'results/exp_001/train'
proj.run_stage(train_cfg, isolated=True)  # GPU stage in subprocess

# Save the full pipeline config for reproducibility
proj.save_snapshot('results/exp_001')
```

**How auto-discovery works:**
Given `save_dir = "results/exp_001/train"`, `run_stage` looks at `results/*/train/` for all sibling experiment directories with the same stage name. This means re-running a pipeline with different parameters will automatically find cached stages from previous experiments.

---

### `proj.save_snapshot()`: Save Pipeline Config

Save the current project defaults as `pipeline.yaml` for reproducibility.

```python
proj.save_snapshot('results/exp_001')
# Creates results/exp_001/pipeline.yaml
```

The saved `pipeline.yaml` can later be re-run with:
```bash
flexlock-run -c results/exp_001/pipeline.yaml -s train
```

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
    _snapshot_=dict(
        repos={'main': '.'},          # string shorthand
        data={'train_data': '${...input_data}'}
    )
)

# Now FlexLock tracks:
# - Code version (git tree hash)
# - Data version (file hash)
# - Configuration
```

> **Note:** Use `_snapshot_=` inside `py2cfg`. The `snapshot_config=` spelling only works as a parameter to the `@flexcli` decorator.

To track only specific files within a repo (speeds up `smart_run` by ignoring irrelevant changes):

```python
_snapshot_=dict(
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
_snapshot_=dict(
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
