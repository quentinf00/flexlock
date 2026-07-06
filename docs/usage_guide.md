# FlexLock Usage Guide

A practical, end-to-end tour of the library. Each section answers one
question: *what does this give me, and how do I get it?*

## Table of Contents

1. [Overview](#1-overview)
2. [Installation & first run](#2-installation--first-run)
3. [Configuration model](#3-configuration-model)
4. [Submitting work — three flavors](#4-submitting-work--three-flavors)
5. [`py2cfg` — build configs from Python](#5-py2cfg--build-configs-from-python)
6. [Sweeps](#6-sweeps)
7. [Snapshots & reproducibility](#7-snapshots--reproducibility)
8. [Smart run / caching](#8-smart-run--caching)
9. [HPC backends](#9-hpc-backends)
10. [MLflow integration](#10-mlflow-integration)
11. [Debugging](#11-debugging)
12. [Exceptions](#12-exceptions)
13. [Environment variables](#13-environment-variables)
14. [Common recipes](#14-common-recipes)
15. [FAQ / gotchas](#15-faq--gotchas)

---

## 1. Overview

FlexLock is a thin orchestration layer around OmegaConf and Python's
`multiprocessing` / Slurm / PBS. It runs the same function you'd write
anyway, and gives you three things in return:

1. **A reproducible `save_dir`.** Every submission resolves `save_dir`
   eagerly (so resolvers like `${vinc:}` advance exactly once) and writes
   `run.lock` before the function runs.
2. **A snapshot of the environment.** Git tree hash for tracked repos,
   xxh64 of tracked data files, the resolved config — all in `run.lock`.
3. **A cache.** When you submit the same fingerprint again, FlexLock
   returns the cached result instead of re-executing.

It sits between Hydra (config composition) and a job scheduler (Slurm,
PBS, local multiprocessing): you write the function, FlexLock handles
config merging, save-dir lifecycle, snapshotting, parallel dispatch, and
cache lookup.

---

## 2. Installation & first run

```bash
pip install flexlock
# or
conda install -c quentinf00 flexlock
```

Minimal "hello world":

```python
# train.py
from flexlock import flexcli

@flexcli
def train(lr: float = 0.01, epochs: int = 10, save_dir: str = 'outputs/train'):
    """Train a model."""
    print(f"lr={lr}, epochs={epochs}, save_dir={save_dir}")
    return {"accuracy": 0.95}

if __name__ == "__main__":
    train()
```

```bash
python train.py -o lr=0.1
```

After the run, `outputs/train/` contains:

```
outputs/train/
├── run.lock         # config + git tree hash + data hashes, written before exec
├── run.complete     # written after the function returns; cache-hit marker
├── results.json     # the function's return value (if dict-shaped)
└── snapshot/        # filtered git tree if you snapshot repos / data
```

`run.lock` is the canonical record. `run.complete` is what
`smart_run` looks for to decide a run is a real cache hit (a run with
only `run.lock` was interrupted).

---

## 3. Configuration model

FlexLock configs are OmegaConf `DictConfig`s. A config that should *run*
something carries a `_target_` key whose value is a dotted import path:

```yaml
# config.yaml
_target_: myproject.train.train
lr: 0.01
epochs: 100
save_dir: outputs/train
```

At submit time, FlexLock recursively instantiates any nested dict that
has `_target_`, then calls the top-level target with the remaining keys
as keyword arguments.

### Defaults files

A "defaults" file exports a dict (or `DictConfig`) under a named
variable. Three forms are accepted by `-d` and `Project(defaults=...)`:

```bash
# Dotted module path — variable is the last segment
flexlock-run -d myproject.config.defaults

# File path with explicit variable
flexlock-run -d configs/defaults.py:defaults

# Bare file path — defaults to the `defaults` variable
flexlock-run -d configs/defaults.py
```

The file-based forms register the loaded file in `sys.modules` under
its file stem, so any `_target_` strings captured by `py2cfg` inside the
file remain importable when workers re-import them later. `flexlock-run`
also inserts the current working directory into `sys.path`, so dotted
imports of project-root packages work without `PYTHONPATH=.`.

### Overrides and selection

The merge order for `flexlock-run` is:

```
defaults  +  -c yaml  +  -m merge_file  +  -o root.overrides
           → -s select_node
           +  -M post-select merge  +  -O post-select overrides
           → execute / sweep
```

`-O` and `-M` apply *after* selection, so you can override the selected
node without disturbing the root.

### Relative interpolations

Within a node, prefer relative refs over root-scope refs. They're the
only kind of cross-key reference that survives `proj.get()` *and*
follows per-item sweep overrides:

```python
# myproject/configs.py
from flexlock import py2cfg
from myproject.train import train

defaults = dict(
    train=py2cfg(
        train,
        save_dir='outputs/train',
        log_dir='${.save_dir}/logs',         # sibling key — relative
        ckpt_dir='${.save_dir}/checkpoints', # sibling key — relative
    ),
)
```

`${.x}` resolves against the current node, `${..x}` against its parent,
`${...x}` against its grandparent. These are preserved by `proj.get()`
and by sweep merging, so per-item `save_dir` overrides correctly
propagate into `log_dir` and `ckpt_dir`. Root-scope refs (`${root_anchor}`,
`${main.save_dir}`) are *frozen to their concrete value* at `proj.get()`
time, which keeps the returned sub-tree pickleable for HPC dispatch.

### `${vinc:path}` — auto-numbered run dirs

```python
save_dir='${vinc:outputs/train/run}'
# → outputs/train/run_0000, run_0001, ...
```

`vinc` scans the parent dir for existing matches, picks the next free
slot, and returns the path. FlexLock resolves `save_dir` **once per
submit**, so `${vinc:}` advances the counter exactly once per call
(deterministic per submit) — `run.lock` and `run.complete` always land
in the same directory, even though both phases read `cfg.save_dir`.

Other resolvers: `${now:%Y%m%d}` (timestamp), `${latest:glob_pattern}`
(newest match), `${run_lock:<run_dir>,<dotted.key>}` (read a value from
an upstream `run.lock`).

---

## 4. Submitting work — three flavors

### 4a. CLI via `@flexcli` + `flexlock-run`

For scripts you'll mostly run from the shell:

```python
# train.py
from flexlock import flexcli

@flexcli
def train(lr: float = 0.01, save_dir: str = 'outputs/train'):
    """Train a model."""
    return {"accuracy": 0.95}

if __name__ == "__main__":
    train()
```

```bash
python train.py -o lr=0.1
flexlock-run -d train.train -O lr=0.1     # equivalent
flexlock-run --help                        # prints argparse help + compiled config
```

You get an `ExecutionResult.result` back (the dict), `run.lock`,
`run.complete`, and `results.json` on disk.

### 4b. Python `Project().submit(cfg)`

For multi-stage scripts and notebooks where you want pipeline plumbing
(`proj.get`, `proj.defaults`, `proj.run_stage`, ...):

```python
from flexlock import Project

proj = Project(defaults='myproject.configs.defaults')

cfg = proj.get('train')
cfg.lr = 0.1
result = proj.submit(cfg)

print(result.save_dir)         # 'outputs/train'
print(result.status)           # 'SUCCESS' or 'CACHED'
print(result['accuracy'])      # dict-like access to result.result
```

`proj.get(key)` returns a self-contained sub-tree: root-scope refs are
frozen, resolver calls and intra-node refs are preserved.

### 4c. `from flexlock import submit` — one-shot

For when you already have a `DictConfig` and don't need a Project:

```python
from flexlock import submit, py2cfg
from myproject.train import train

cfg = py2cfg(train, lr=0.01, save_dir='outputs/train')
result = submit(cfg, slurm_config='configs/slurm_gpu.yaml')
```

`submit` is `Project().submit` with all the same kwargs (`sweep`,
`smart_run`, `overrides`, `force`, `isolated`, ...). Use it for ad-hoc
one-offs and library code that takes a config and runs it.

---

## 5. `py2cfg` — build configs from Python

`py2cfg` reads a function/class signature and produces a config dict
keyed by `_target_`:

```python
from flexlock import py2cfg
from myproject.train import train
from myproject.models import Transformer

cfg = py2cfg(
    train,
    lr=0.01,
    model=py2cfg(Transformer, layers=12, heads=16),
    save_dir='outputs/train',
)
# {
#   '_target_': 'myproject.train.train',
#   'lr': 0.01,
#   'epochs': 10,                       # captured from signature default
#   'model': {'_target_': 'myproject.models.Transformer', 'layers': 12, 'heads': 16},
#   'save_dir': 'outputs/train',
# }
```

Use it when:
- you want to refactor a function and have its config follow (signature
  changes propagate automatically),
- you want nested instantiation (`model=py2cfg(...)`),
- you want IDE autocomplete and type-checking on the keyword names.

Prefer YAML when configs are written by non-Python users, or when you
want a declarative record that lives outside the codebase.

**Gotchas:**
- The target must be re-importable on workers. `py2cfg(train)` inside a
  notebook produces `_target_: __main__.train`, which won't import in a
  spawned subprocess. Move definitions to a module.
- Every default in the signature ends up in the config, including
  `None` defaults. Drop them via overrides if you don't want them in
  `run.lock`.
- Decorated functions are unwrapped automatically (`py2cfg` looks at
  `_original_fn`).

---

## 6. Sweeps

A sweep is a list of override dicts merged into the base config one at
a time. Sources:

```python
proj.submit(cfg, sweep=[{'lr': 0.001}, {'lr': 0.01}])              # inline
proj.submit(cfg, sweep_file='configs/grid.yaml')                    # not directly — see below
flexlock-run -d ... --sweep-file configs/grid.yaml
flexlock-run -d ... --sweep "0.001,0.01,0.1" --sweep-target lr
flexlock-run -d ... --sweep-key param_grid                          # list lives in defaults
```

From Python, use `load_sweep` to read a file:

```python
from flexlock import load_sweep, Project

proj = Project(defaults='myproject.configs.defaults')
sweep = load_sweep(sweep_file='configs/grid.yaml')

if __name__ == "__main__":
    results = proj.submit('train', sweep=sweep, n_jobs=4)
    for r in results:
        print(r.save_dir, r['accuracy'])
```

### `sweep_target`

Without `sweep_target`, each item is merged at the root of the base
config. With `sweep_target='optimizer.lr'`, scalar items are placed at
that dotted path.

### `sweep_dir_suffix`

When `True`, each item's `save_dir` becomes
`<base.save_dir>/sweep_{i:04d}/` — items are **nested under** the
sweep root, not siblings to it. This keeps the tasks DB and lineage
markers inside the same tree:

```python
proj.submit(cfg, sweep=sweep, sweep_dir_suffix=True)
# outputs/train/sweep_0000/
# outputs/train/sweep_0001/
# outputs/train/run.lock.tasks.db
```

Containment is validated up-front: if a sweep item's `save_dir` falls
outside the sweep root, you get a `FlexLockValidationError` listing the
offenders before any work is queued.

### Per-item interpolations

Because relative refs (`${.x}`, `${..x}`) survive node selection and
sweep merging, a sweep that overrides `save_dir` automatically updates
sibling keys that point to it:

```python
from flexlock import py2cfg, Project
from myproject.train import train

cfg = py2cfg(
    train,
    save_dir='outputs/train',
    log_dir='${.save_dir}/logs',          # follows per-item save_dir
    ckpt_dir='${.save_dir}/ckpts',
)

if __name__ == "__main__":
    proj = Project()
    proj.submit(cfg, sweep=[
        {'save_dir': 'outputs/sweep/a'},  # log_dir → outputs/sweep/a/logs
        {'save_dir': 'outputs/sweep/b'},  # log_dir → outputs/sweep/b/logs
    ], n_jobs=2)
```

### `n_jobs`, `isolated`, and the `__main__` guard

- `n_jobs=1` (default, no `isolated`): runs in-process. No guard needed.
- `n_jobs > 1` or `isolated=True`: uses `multiprocessing` with the
  `spawn` start method (avoids CUDA fork hazards). Spawn re-imports the
  launching script in each child, so **any module-scope
  `proj.submit(...)` call must sit under `if __name__ == "__main__":`**
  or the children will recursively re-launch.
- Notebooks and REPL contexts are fine.

After a parallel or `isolated=True` run, workers write
`results.json` into each per-task `save_dir`. The driver loads them
back and populates `ExecutionResult.result`, so the return value is
available downstream just like in serial execution.

---

## 7. Snapshots & reproducibility

Every submit with a `save_dir` writes `run.lock` with three sections:

```yaml
# outputs/train/run.lock
timestamp: "2026-06-01T14:30:00"
repos:
  myproject:
    commit: "abc123…"
    tree: "def456…"               # this is what smart_run compares
    is_dirty: false
    path: "/abs/path/to/repo"
data:
  train_data: "xxh64_789xyz…"
config:
  _target_: myproject.train.train
  lr: 0.01
  save_dir: outputs/train
```

### Declaring what to track

```python
from flexlock import py2cfg
from myproject.train import train

cfg = py2cfg(
    train,
    input_path='data/train.csv',
    save_dir='outputs/train',
    _snapshot_=dict(
        repos={
            'myproject': '.',                       # string shorthand → {'path': '.'}
            'mylib': {'path': 'libs/mylib'},        # explicit
            'pkg':   {'module': 'pkg'},             # resolved via importlib
            'filtered': {                           # filtered comparison
                'path': '.',
                'include': ['src/model/**'],
                'exclude': ['tests/**'],
            },
        },
        data={'train': '${.input_path}'},
        prevs=['${.upstream_run_dir}'],             # link to upstream runs
    ),
)
```

When a config has `_target_`, FlexLock auto-tracks the git repo of the
target's source file — you don't need to spell `repos` for the main
codebase. Add explicit entries for sibling libraries, vendored
dependencies, or filtered comparisons.

### `snapshot()` directly

You can also write a snapshot outside the `submit` flow:

```python
from flexlock import snapshot

snapshot(cfg, repos={'main': '.'}, data={'train': 'data/train.csv'})
```

### Re-running from a snapshot

`run.lock` is YAML — pull the `config` block out and resubmit it:

```python
from omegaconf import OmegaConf
from flexlock import submit

cfg = OmegaConf.load('outputs/train/run.lock').config
submit(cfg, force=True)   # re-execute, overwriting in place
```

`force=True` invalidates `run.complete` (so `smart_run` doesn't short-
circuit), preserves outputs and `run.lock`, and re-runs the function.

---

## 8. Smart run / caching

```python
proj.submit(cfg, smart_run=True, search_dirs=['outputs/train/'])
```

Mechanism:

1. Compute a stable **fingerprint** from `cfg` (per-repo git *tree* hashes
   restricted to include/exclude, data hashes, and the resolved config with
   `save_dir` prefix-normalized so output location doesn't affect it). This
   uses `git write-tree` only — no commits or refs are created.
2. Look the fingerprint up in the project-wide index (one indexed `SELECT`).
   The index maps a fingerprint to where a completed run lives — a `run.lock`
   directory **or** a sweep task `(task_db, task_id)`, so sweep items are
   first-class cache entries.
3. On a hit, verify the pointed-to run still exists and is complete
   (`run.complete`, or the task's `results.json`). A stale pointer self-prunes
   and is treated as a miss. Only `status='done'` runs are ever served.
4. On an index miss, fall back to the legacy `**/run.lock` glob scan +
   `RunDiff` (controlled by `FLEXLOCK_INDEX_FALLBACK`, default on) and backfill
   the index on a hit, so the slow path self-eliminates.

Rebuild the index at any time with `flexlock reindex <results_root>`; deleting
it is always safe.

### When caches miss

- The git tree hash changed (any tracked file modified, including
  untracked-but-not-ignored files).
- A tracked data path's xxh64 changed.
- The config changed (after resolution, ignoring `_snapshot_`).
- The candidate run never wrote `run.complete`.

To debug a miss:

```bash
flexlock-diff outputs/train/run_0001 outputs/train/run_0002
```

### Knobs

| Knob                                | Effect                                     |
|-------------------------------------|--------------------------------------------|
| `smart_run=False`                   | Always execute                             |
| `force=True`                        | Invalidate `run.complete` (and, for sweeps, per-item markers + the task DB), then execute |
| `FLEXLOCK_NO_CACHE=1`               | Disable the on-disk data-hash cache        |
| `FLEXLOCK_INDEX=/path/index.db`     | Explicit fingerprint-index location        |
| `FLEXLOCK_INDEX_FALLBACK=0`         | Skip the legacy glob scan on an index miss |
| `match_include` / `match_exclude`   | Override git path filters at compare time  |
| `search_dirs=[...]`                 | Where to look for cached runs              |

Combine with sweeps: re-running a 32-job sweep with `smart_run=True`
re-executes only the ones whose fingerprints don't match an existing
completed run.

---

## 9. HPC backends

Slurm and PBS are supported via YAML config files. The same path works
for `submit` (single job) and `submit(..., sweep=..., n_jobs=N)` (array
job).

```yaml
# configs/slurm_gpu.yaml
startup_lines:
  - "#SBATCH --job-name=flexlock"
  - "#SBATCH --gres=gpu:1"
  - "#SBATCH --cpus-per-task=8"
  - "#SBATCH --mem=32G"
  - "#SBATCH --time=04:00:00"
  - "#SBATCH --array=0-31"
  - "module load cuda/11.8"
  - "source activate myenv"
python_exe: "python"
```

```python
proj.submit(cfg, sweep=sweep, slurm_config='configs/slurm_gpu.yaml')
```

```yaml
# configs/pbs_gpu.yaml — container example
startup_lines:
  - "#PBS -l select=1:ncpus=8:mem=32gb"
  - "#PBS -l walltime=04:00:00"
  - "#PBS -J 0-31"
  - "cd $PBS_O_WORKDIR"
python_exe: |
  singularity run --nv
  --bind $(pwd):/workspace --pwd /workspace
  env.sif python
```

`wait=False` submits and returns immediately. `wait=True` blocks until
the array finishes; the default timeout comes from
`FLEXLOCK_DEFAULT_TIMEOUT` (seconds).

Preview the rendered submission script without submitting:

```python
proj.submit(cfg, slurm_config='configs/slurm_gpu.yaml', dry_run=True)
# Prints the generated Slurm script plus any validation warnings.
```

Anything that goes wrong on the backend side — bad YAML, queue
rejection, task-DB lock contention — is raised as
`FlexLockBackendError`.

---

## 10. MLflow integration

`mlflow_context` wraps an MLflow run that's bound to a physical
`save_dir`. It implements an "always new + deprecate old" strategy so
re-runs into the same directory don't pollute the previous MLflow run:

```python
from flexlock import flexcli, mlflow_context
import mlflow

@flexcli
def train(lr: float = 0.01, save_dir: str = 'outputs/train'):
    with mlflow_context(save_dir, experiment_name='my-exp') as run:
        mlflow.log_metric('train_loss', 0.32)
        mlflow.log_metric('val_accuracy', 0.95)
    return {"accuracy": 0.95}

if __name__ == "__main__":
    train()
```

The context inherits user tags from the previously active run for the
same directory, so pipeline tags like `pipeline_run=run_001` persist
across stages without manual plumbing. MLflow not installed? The
context is a no-op and yields `None`.

---

## 11. Debugging

### `@debug_on_fail`

```python
from flexlock import debug_on_fail

@debug_on_fail
def train(...):
    ...
```

On exception, the decorator either drops you into PDB (script context)
or injects the function's locals into the caller's scope (notebook
context). Strategy is chosen by `FLEXLOCK_DEBUG_STRATEGY`:

| Value        | Behavior                                           |
|--------------|----------------------------------------------------|
| `auto` (default) | PDB for scripts, locals injection for notebooks |
| `pdb`        | Always PDB post-mortem                             |
| `inject`     | Always inject locals                               |

### Activation

Two control surfaces, two semantics:

- **`@flexcli` / `flexlock-run --debug`:** opt *in* to wrapping the user
  function with `debug_on_fail`. `FLEXLOCK_DEBUG=1` (or `--debug`)
  enables it.
- **Manually applied `@debug_on_fail`:** active by default. To turn it
  off (e.g. in production), set `FLEXLOCK_NODEBUG=1` — the decorator
  returns the original function unchanged. Note: `FLEXLOCK_DEBUG=0` does
  *not* disable a manually applied decorator.

The decorator accepts (and warns about) legacy kwargs like
`stack_depth=`, so old snippets won't blow up — they're just ignored.

### `print_config`

```bash
flexlock-run -d configs/defaults.py -s train -O lr=0.1 --print-config
```

Prints the fully-merged config plus the target function's docstring,
then exits. From Python:

```python
proj.submit('train', overrides={'lr': 0.1}, print_config=True)
# When sweep is also passed, prints one config per sweep item.
```

`flexlock-run --help` prints argparse help followed by the same
compiled config view.

### Logging to file

```python
from pathlib import Path
from flexlock import flexcli, log_to_file
from loguru import logger

@flexcli
def train(lr: float = 0.01, save_dir: str = 'outputs/train'):
    with log_to_file(Path(save_dir) / 'debug.log'):
        logger.debug(f"starting with lr={lr}")
        ...
```

`log_to_file` is a context manager that adds a Loguru sink for its
lifetime and removes it on exit. Importable from the package root.

---

## 12. Exceptions

All FlexLock exceptions inherit from `FlexLockError`.

| Exception                  | Wraps                                                                 |
|----------------------------|-----------------------------------------------------------------------|
| `FlexLockConfigError`      | Invalid config structure, bad `_target_`, malformed `_snapshot_`     |
| `FlexLockValidationError`  | Sweep `save_dir` containment, ambiguous sweep source, missing select |
| `FlexLockSnapshotError`    | Can't write `run.lock`, git/data hash failures                       |
| `FlexLockCacheError`       | Cache read / fingerprint comparison failures                          |
| `FlexLockExecutionError`   | FlexLock-side dispatch failures (NOT user exceptions — see below)    |
| `FlexLockBackendError`     | Slurm/PBS submission failures, queue errors, task DB lock issues     |

**Important:** exceptions raised *inside the user's target function*
are **not** wrapped. They propagate as the original type
(`ValueError`, `RuntimeError`, ...). Catch them directly:

```python
from flexlock import FlexLockBackendError

try:
    result = proj.submit(cfg, slurm_config='configs/slurm_gpu.yaml')
except FlexLockBackendError as e:
    print(f"HPC failed: {e}")
except ValueError as e:
    print(f"User function raised: {e}")
```

---

## 13. Environment variables

| Variable                       | Default                  | Effect                                                  |
|--------------------------------|--------------------------|---------------------------------------------------------|
| `FLEXLOCK_DEBUG`               | `false`                  | Opt into debug wrapping via `@flexcli` / `flexlock-run` |
| `FLEXLOCK_NODEBUG`             | `false`                  | Disable a manually applied `@debug_on_fail`             |
| `FLEXLOCK_DEBUG_STRATEGY`      | `auto`                   | `auto` / `pdb` / `inject`                               |
| `FLEXLOCK_NO_CACHE`            | `false`                  | Disable on-disk data-hash cache                         |
| `FLEXLOCK_CACHE`               | `~/.cache`               | Cache base dir                                          |
| `FLEXLOCK_DEFAULT_N_JOBS`      | `1`                      | Default `--n_jobs` if not given                         |
| `FLEXLOCK_DEFAULT_TIMEOUT`     | `3600`                   | HPC wait timeout (seconds)                              |
| `FLEXLOCK_POLL_INTERVAL`       | `10`                     | HPC poll interval (seconds)                             |
| `FLEXLOCK_WARN_SMART_RUN`      | `true`                   | Warn when `smart_run=True` and `search_dirs=None`       |
| `FLEXLOCK_TIMESTAMP_FORMAT`    | `%Y-%m-%dT%H-%M-%S`      | Directory timestamp format                              |
| `FLEXLOCK_CONFIGURE_LOGGING`   | `true`                   | Configure Loguru on import                              |

Boolean values accept `1`/`true`/`yes`/`on` and `0`/`false`/`no`/`off`.
See [reference.md](./reference.md) for the full list.

---

## 14. Common recipes

### 14a. 16-job hyperparameter sweep on Slurm

```python
# scripts/sweep.py
from flexlock import Project, load_sweep

if __name__ == "__main__":
    proj = Project(defaults='myproject.configs.defaults')
    sweep = [{'lr': lr, 'batch_size': bs}
             for lr in [0.001, 0.01, 0.1, 1.0]
             for bs in [16, 32, 64, 128]]   # 16 items

    results = proj.submit(
        'train',
        sweep=sweep,
        sweep_dir_suffix=True,
        slurm_config='configs/slurm_gpu.yaml',  # set #SBATCH --array=0-15
        smart_run=True,
    )

    best = max(results, key=lambda r: r.get('val_accuracy', 0))
    print(f"best: {best.save_dir} → {best['val_accuracy']}")
```

### 14b. Resume a partially-finished sweep

Re-run the same script. `smart_run=True` skips every completed item
(has both `run.lock` and `run.complete`); only interrupted items
re-execute. No special command needed.

### 14c. Re-run only the runs that failed

```python
from pathlib import Path
from flexlock import Project

proj = Project(defaults='myproject.configs.defaults')

# Items that started but didn't complete
incomplete = [d for d in Path('outputs/sweep').glob('sweep_*/')
              if (d / 'run.lock').exists() and not (d / 'run.complete').exists()]

if __name__ == "__main__":
    for d in incomplete:
        cfg = proj.get('train')
        cfg.save_dir = str(d)
        proj.submit(cfg, force=True)   # re-exec into same dir
```

### 14d. Pull sweep results back as a DataFrame

```python
import pandas as pd

rows = []
for r in results:        # list[ExecutionResult] from proj.submit(..., sweep=...)
    rows.append({
        'save_dir': r.save_dir,
        'lr': r.cfg.lr,
        'batch_size': r.cfg.batch_size,
        'accuracy': r.get('accuracy'),
    })
df = pd.DataFrame(rows)
```

### 14e. Single isolated GPU run

When you want the child's CUDA context to die at exit (so a later
sweep can fork without the parent holding a stale CUDA handle):

```python
from flexlock import submit, py2cfg
from myproject.train import train

cfg = py2cfg(train, lr=0.01, save_dir='outputs/train')

if __name__ == "__main__":
    result = submit(cfg, isolated=True)
    print(result['accuracy'])
```

### 14f. Multi-stage pipeline with auto-discovery

```python
from flexlock import Project

proj = Project(defaults='myproject.configs.defaults')

prep_cfg = proj.get('preprocess')
prep_cfg.save_dir = 'outputs/exp_001/preprocess'
proj.run_stage(prep_cfg)

train_cfg = proj.get('train')
train_cfg.data_dir = prep_cfg.save_dir         # propagated by run_stage
train_cfg.save_dir = 'outputs/exp_001/train'
proj.run_stage(train_cfg, isolated=True)

proj.save_snapshot('outputs/exp_001')          # writes pipeline.yaml
```

`run_stage` auto-discovers `search_dirs` by scanning sibling experiment
directories with the same stage name, so re-running with different
hyperparameters cache-hits where it can.

---

## 15. FAQ / gotchas

**Why must I use `if __name__ == "__main__":` for sweeps?**
`n_jobs > 1` and `isolated=True` use `multiprocessing.spawn` (chosen to
avoid CUDA-fork hazards). Spawn re-imports your launching script in
every worker — without the guard, the worker re-runs `proj.submit(...)`
recursively. Notebooks/REPL are fine.

**Why is `save_dir` resolved eagerly?**
Resolvers like `${vinc:}` inspect the filesystem. If `cfg.save_dir`
were re-resolved at each access, the snapshot phase and the
complete-marker phase would land in different dirs (each call would
advance the version counter). FlexLock resolves it once at submit time
and freezes the string.

**`results.json` is empty after my sweep — what happened?**
The user function returned `None` or a non-dict value. `results.json`
gets `{"result": <value>}` when the return value isn't already a dict.
The driver still loads it back into `ExecutionResult.result`.

**`_target_` fails to import on workers — why?**
Workers re-import the target's module from scratch. If the target lives
in `__main__` (e.g. defined in a notebook or in a script run as
`python script.py`), the worker can't find it. Move the function to a
module and re-run.

**My relative ref `${.x}` got frozen to a literal string — why?**
That happens if you pull the node through `OmegaConf.to_container(...,
resolve=True)` and rebuild it. `proj.get()` is designed to preserve
relative refs; manual round-trips are not.

**`smart_run` keeps missing my cache — why?**
Most common causes: (1) a tracked file in the repo is dirty or
untracked-but-not-ignored, bumping the git tree hash. (2) A data path
changed. (3) The candidate run never wrote `run.complete` (interrupted).
Run `flexlock-diff cur_dir cached_dir` to see exactly what differs.

**I used `${main.save_dir}` and sweep overrides don't propagate.**
Cross-tree refs (`${main.save_dir}`, `${root_anchor}`) are frozen to
their concrete value at `proj.get()` time. Use intra-node refs
(`${.save_dir}`, `${..save_dir}`) for anything that should follow
per-item sweep overrides.

**`flexlock-run -d myproject/defaults.py` works, but
`-d myproject.defaults` says it can't find `defaults`.**
For dotted form, the *last* segment is the variable name, not the
file. `myproject.defaults` means `from myproject import defaults`. If
your layout is `myproject/defaults.py` with `defaults = {...}` inside,
use `myproject.defaults.defaults` or `myproject/defaults.py`.

---

## See also

- [CLI Reference](./cli_reference.md)
- [Python API](./python_api.md)
- [HPC Integration](./hpc_integration.md)
- [Resolvers](./resolvers.md)
- [Debugging](./debugging.md)
- [Reference (env vars + exceptions)](./reference.md)
