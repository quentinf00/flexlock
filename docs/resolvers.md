# OmegaConf Resolvers

FlexLock registers custom OmegaConf resolvers for dynamic configuration values.

## Binding times

Config values are produced at four distinct moments. Match the mechanism to the
moment:

| Binding time      | Mechanism                                    |
|-------------------|----------------------------------------------|
| submit-time       | plain interpolation (`${a.b}`), resolved eagerly when a stage is selected/submitted |
| submit-time       | `${run:<preset>,<select>}`: the newest complete run of a preset, fixed when you submit (also by `--dump`/`--enqueue`) |
| `save_dir` collision / naming | `save_dir_policy=` on `submit()`/`run` (see below) |
| stage-start       | deferred resolvers `${run_lock:}` / `${latest:}`, fired once on the worker |
| per-sweep-item    | the sweep item is merged **before** resolution, so `${variable}` sees it |

## `save_dir_policy` (replaces `${vinc:}` / `${now:}`)

Configs keep a **stable** `save_dir`. The policy decides what happens when that
directory is already *occupied* — i.e. contains a `run.lock` from a previous
run (`run.complete` marks it finished; `run.lock` alone means crashed or
in-flight):

| policy | behaviour when `save_dir` is occupied |
|--------|----------------------------------------|
| `"raise"` (default, `None`) | refuse: raise `FlexLockValidationError` |
| `"increment"` | version the base (`run` → `run_0000`, `_0001`, …), **claimed atomically** — never collides |
| `"overwrite"` | delete the dir's contents, then run (never touches a dir *without* `run.lock`) |
| `"skip"` | don't execute; return the existing **complete** run's result (raises if the occupant is incomplete) |
| `"unsafe"` | run in place, no check (pre-0.8 behaviour) |
| `"timestamp"` | `save_dir/<timestamp>` — never collides |

```python
proj.submit(cfg)                                 # raises if save_dir holds a run
proj.submit(cfg, force=True)                     # explicit in-place rerun
proj.submit(cfg, save_dir_policy="increment")    # fresh versioned dir every run
```

```bash
flexlock-run ... --save-dir-policy increment
flexlock-run ... --force        # rerun a crashed/stale run in place
```

Interaction rules:

- **`smart_run` wins first**: a matching complete run is returned from cache
  before the guard fires — the guard only sees genuine conflicts (crashed
  runs, changed configs, `smart_run=False`).
- **`force=True` bypasses the default guard** (it invalidates `run.complete`
  and reruns in place).
- **Sweeps**: a naming policy applies once to the sweep root; the guard is
  enforced *per item* after the per-item cache check. `"skip"` on a sweep
  means **resume**: complete items are reused, crashed items rerun in place.
- The policy is applied after `print_config` / `--check` / `dry_run`, which
  therefore never create or delete anything.

### Migration

| Old (deprecated)                         | New                                   |
|------------------------------------------|---------------------------------------|
| `save_dir: ${vinc:outputs/run}`          | `save_dir: outputs/run` — keep it stable; rely on the default guard + `--force`, or pass `save_dir_policy="increment"` where accumulating versions is wanted |
| `save_dir: outputs/run/${now:%Y%m%d}`    | `save_dir: outputs/run` + `save_dir_policy="timestamp"` |

`${vinc:}` and `${now:}` still work for one deprecation cycle but emit a
`DeprecationWarning`.

## Available Resolvers

### `${now:format}` - Current Timestamp

> **Deprecated.** Prefer `save_dir_policy="timestamp"`. See migration above.

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

### `${run:preset,select[,pin][,strict]}` - Newest Run of a Preset

The directory of the newest **complete** run of a preset (the `-d` target +
`-s` key it was launched with; see the usage guide, §7 "Presets"). Use it
instead of copying a versioned path such as `results/train_x_0005`.

```python
infer = dict(
    train_dir="${run:xps_glob.train_small_cloud_gap,main}",
    main=py2cfg(infer_fn, xp_path="${train_dir}",
                checkpoint="${train_dir}/checkpoints/best_model.ckpt", ...),
)
```

```bash
# pin a version (the run whose dir name, or path, ends with the pin)
flexlock-run -d my.xps.infer -s main -o 'train_dir=${run:xps_glob.train_x,main,0005}'
# only runs launched without -o/-O/-m/-M overrides
flexlock-run -d my.xps.infer -s main -o 'train_dir=${run:xps_glob.train_x,main,strict}'
```

**Behavior:**
- Any run of the preset matches, whatever its overrides (use `strict`, or a
  separate preset such as `train_x_debug`, to keep quick tests out).
- "Newest" means most recently completed; failed, interrupted and running
  runs are skipped. The preset address matches by suffix
  (`xps_glob.train_x`, `xps_glob:train_x`, `train_x`).
- **Resolved once, at submit** (and by `--dump`, `--enqueue`,
  `--print-config`): the concrete path is what the config, the task DB and
  `run.lock` record, so a job waiting in the queue can't pick a newer run.
  The choice is logged: `${run:xps_glob.train_x,main} → results/train_x_0005`.
- The resolved run is added to `_snapshot_.prevs`, so lineage
  (`flexlock show`/`graph`) records it without a hand-written entry.
- No match is an error that lists the preset's complete runs (or similarly
  named presets). Without a `select`, runs of several `-s` keys are an error.
- Only values containing `${run:` are resolved early; other interpolations in
  the config (e.g. `${.save_dir}/logs`) keep their usual binding time.

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

> **Deprecated.** Prefer `save_dir_policy="increment"`, which also claims the
> directory atomically. See migration above.

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

### `${run_lock:run_dir,key}` - Read from Upstream Run

Read a field from an upstream run's `run.lock` file using a dot-separated key path. Essential for downstream stages that need config values from a training or preprocessing run.

**Usage:**
```yaml
run_dir: results/train_0005
stats_file: ${run_lock:${run_dir},config.datamodule.stats_file}
checkpoint: ${run_lock:${run_dir},config.save_dir}/checkpoints/best.ckpt
```

**With default (optional third argument):**
```yaml
# Returns "none" if the key doesn't exist
optional_field: ${run_lock:${run_dir},config.flow_checkpoint,none}
```

**Python config example — downstream inference from upstream training:**
```python
cfg = dict(
    run_dir="results/train_0005",
    main=py2cfg(inference,
        stats_file="${run_lock:${run_dir},config.datamodule.stats_file}",
        checkpoint="${run_lock:${run_dir},config.save_dir}/checkpoints/best.ckpt",
        prepared_data_dir="${run_lock:${run_dir},config.datamodule.prepared_data_dir}",
        # Override run_dir with -o to point to a different upstream run
    )
)
```

**Override the upstream run from CLI:**
```bash
flexlock-run -d myproject.inference_cfg -s main \
    -o run_dir=results/train_0008
```

**Behavior:**
- Reads `run_dir/run.lock` and navigates the dot-path (e.g., `config.datamodule.stats_file`)
- Supports nested keys to any depth
- Optional third argument provides a default if the key is missing or null
- Raises `FileNotFoundError` if `run.lock` doesn't exist (unless default given)
- Raises `KeyError` if key path doesn't exist (unless default given)
- Not cached (`use_cache=False`) — re-reads on each resolution, so changing `run_dir` via `-o` works correctly

---

### Template configs with a single anchor

Put one top-level variable in your `defaults` dict. All downstream
templates derive their input paths from it via `${run_lock:}`:

```python
defaults = dict(
    cnf_run_dir="${latest:outputs/cnf_train/run_*}",
    eval=py2cfg(evaluate,
        data_dir="${run_lock:${cnf_run_dir},config.data_dir}",
        model_dir="${run_lock:${cnf_run_dir},config.save_dir}",
        save_dir="outputs/eval/run",   # + --save-dir-policy increment
    ),
)
```

Override from CLI:  `flexlock-run -d defaults -s eval -o cnf_run_dir=outputs/cnf_train/run_0003`
Override from API:  `OmegaConf.update(proj.cfg, 'cnf_run_dir', result.save_dir)`

---

## Using Resolvers

### In YAML Configs

```yaml
# config.yaml
_target_: myproject.train

# Dynamic timestamp
save_dir: outputs/train_${now:%Y%m%d_%H%M%S}

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
    input_data='data/train.csv'
)

# Resolve all interpolations
resolved = OmegaConf.to_container(cfg, resolve=True)
print(resolved['save_dir'])  # "outputs/train_20240115_143000"
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
# Use resolvers in paths
checkpoint: ${latest:${base_dir}/checkpoints/epoch_*.pth}

# Combine timestamp and versioning
save_dir: ${vinc:outputs/train_${now:%Y%m%d}/run}
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
  save_dir: outputs/preprocess/run

# Stage 2: Train (depends on Stage 1)
train:
  _target_: myproject.train
  preprocess_dir: ${latest:outputs/preprocess/run_*/}
  save_dir: outputs/train/run
```

Run each stage with `--save-dir-policy increment` (or rely on the default
guard when a stage should run exactly once per directory).

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

### 1. Use `save_dir_policy="increment"` for Sequential Runs

```python
# Good: Auto-versioning, atomic claim, no resolver side effects
cfg = py2cfg(train, save_dir='outputs/exp/run')
proj.submit(cfg, save_dir_policy="increment")

# Bad: Manual versioning (error-prone)
cfg = py2cfg(train, save_dir='outputs/exp/run_0042')
```

### 2. Reference upstream runs by preset, not by path

```python
# Best: the newest complete run of the upstream preset, recorded at submit
train_cfg = py2cfg(train, preprocess_dir='${run:xps.preprocess,main}')

# Good: Automatically finds latest upstream by glob (mtime, any run)
train_cfg = py2cfg(
    train,
    preprocess_dir='${latest:outputs/preprocess/run_*}'
)

# Bad: Hardcoded path (breaks when preprocess reruns)
train_cfg = py2cfg(train, preprocess_dir='outputs/preprocess/run_0001')
```

### 3. Combine Resolvers for Powerful Patterns

```yaml
# Latest data file reference
input_data: ${latest:data/processed_*.csv}

# Pipeline stage with dependency
upstream_dir: ${latest:outputs/stage1/run_*/}
```

### 4. Track Data with Snapshot Config

For data tracking, use `_snapshot_` in `py2cfg` (or `snapshot_config` when using the `@flexcli` decorator):

```python
cfg = py2cfg(
    train,
    input_data='data/train.csv',
    _snapshot_=dict(
        repos={'main': '.'},
        data={'train': '${...input_data}'}
    )
)
```

> **Note:** Use `_snapshot_=` inside `py2cfg`. The `snapshot_config=` spelling only works as a parameter to the `@flexcli` decorator — passing it to `py2cfg` will forward it as an unexpected keyword argument to the function.

---

## See Also

- [OmegaConf Documentation](https://omegaconf.readthedocs.io/) - Interpolation syntax
- [Python API](./python_api.md) - Using resolvers programmatically
- [CLI Reference](./cli_reference.md) - Resolver usage in CLI workflows
