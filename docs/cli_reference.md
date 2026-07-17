# CLI Reference

## `flexlock` — Experiment Management CLI

Unified CLI for listing, tagging, and cleaning up experiment runs.

### `flexlock ls` — List Runs

List all runs (directories containing `run.lock`) under a given path.

```bash
# List runs in current directory
flexlock ls

# List runs under a specific path
flexlock ls results/

# Verbose output (shows _target_ and lineage)
flexlock ls results/ -v

# JSON output (for scripting)
flexlock ls results/ --format json
```

**Output columns:** timestamp, stage name, path, tag (if any)

---

### `flexlock tag` — Tag Runs

Assign a human-readable name to a run directory. Tags are stored as git refs under `refs/flexlock/tags/` and link to all lineage shadow commits as parents, so `git log <tag-ref>` shows the full provenance chain.

```bash
# Tag a run
flexlock tag baseline_v1 results/exp_001/train

# Tag with a message
flexlock tag best_model results/exp_003/train -m "92.5% accuracy on val set"

# List all tags
flexlock tag -l

# List tags with lineage details
flexlock tag -l -v

# Delete a tag
flexlock tag -d baseline_v1
```

**How it works:**
1. Creates a git commit object with the run's lineage shadow commits as parents
2. Stores the commit under `refs/flexlock/tags/<name>`
3. The commit message records the path and timestamp

**Viewing lineage of a tagged run:**
```bash
# Show all linked shadow commits
git log --oneline refs/flexlock/tags/baseline_v1
```

---

### `flexlock gc` — Garbage Collect

Remove untagged run directories. Tagged runs and their lineage dependencies are protected.

```bash
# Dry run — show what would be deleted
flexlock gc results/ -n

# Delete untagged runs (with confirmation prompt)
flexlock gc results/

# Force delete without confirmation
flexlock gc results/ -f

# Also clean orphaned shadow git refs
flexlock gc results/ -f --refs
```

**Protection rules:**
- Tagged runs are never deleted
- Lineage dependencies of tagged runs are protected (recursive)
- Only runs with no tag and no tagged descendant are eligible for deletion

`flexlock gc --incomplete` prunes only run dirs that have `run.lock` but no
`run.complete` (interrupted attempts), with no tag-protection logic.

---

### `flexlock show` — Inspect One Run

Machine-readable status, metadata, lineage, and config for a single run. The
default `md` output is for humans; agents use `--format json` (a stable contract,
see [Agentic Workflows](agentic_workflows.md)).

```bash
flexlock show results/train                    # markdown
flexlock show results/train --format json      # JSON contract
flexlock show results/train --root results/    # scan a specific root for downstream/tags
flexlock show results/train --no-downstream    # skip the downstream scan (faster)
```

`status` is one of `complete | failed | interrupted | running | pending | unknown`.
A failed run attaches its `run.error` payload; a `sweep_master` attaches per-task
`tasks` counts.

### `flexlock graph` — Experiment DAG

Emit the whole results tree as a graph (JSON is the backend for the skills and the
HTML report).

```bash
flexlock graph results/ --format json          # nodes + edges + (with --groups) groups
flexlock graph results/ --format mermaid       # paste into a Mermaid renderer
flexlock graph results/ --format dot           # pipe to graphviz: | dot -Tpng -o dag.png
flexlock graph results/ --format json --groups # add same-tree / same-data groupings
```

Edges are `lineage` or `sweep_item`; lineage sources outside the scanned tree
appear as `kind: external` stub nodes so the graph is closed.

### `flexlock why` — Explain a Difference

Compare two runs: config/data/git diffs plus the real commits between their
recorded shadow commits.

```bash
flexlock why results/run_a results/run_b               # text
flexlock why results/run_a results/run_b --format json # JSON contract
```

Per common repo it reports `trees_identical`, or `a_to_b`/`b_to_a` commit lists.
If the shadow commits were gc'd, a per-repo `error` is set and the command still
exits 0.

### `flexlock stages` — List Runnable Stages

Enumerate every stage (a mapping with `_target_`) in a defaults tree, **without
resolving** the config (so `${vinc:}` never fires or creates directories).

```bash
flexlock stages -d myproject.pipeline.cfg                 # text
flexlock stages -d myproject.pipeline.cfg --format keys   # bare keys (for fzf)
flexlock stages -d myproject.pipeline.cfg --format json   # {key,target,save_dir,depth}
flexlock stages -d myproject.pipeline.cfg -c overrides.yaml
```

fzf recipe:

```bash
DEF=myproject.pipeline.cfg
flexlock-run -d "$DEF" -s "$(flexlock stages -d "$DEF" --format keys | fzf)"
```

### `flexlock report` — Static HTML Report

Render a self-contained, offline-openable HTML report (no CDN) of a results tree.

```bash
flexlock report results/ -o report.html --title "My experiment"
flexlock report results/ -o report.html --embed-configs   # include per-run configs
flexlock report results/ -o report.html --groups          # surface same code/data runs
```

### `flexlock skills` — Manage Shipped Skills

FlexLock ships four Claude Code skills encoding common workflows.

```bash
flexlock skills list                                 # names + descriptions
flexlock skills install                              # install all into .claude/skills
flexlock skills install flexlock-survey --dest .claude/skills
flexlock skills install --force                      # overwrite (= upgrade)
```

---

## `flexlock-diff` — Compare Snapshots

Compare two run snapshots from directories, the task DB, or a mix.

```bash
flexlock-diff dirs results/run_a results/run_b           # human-readable
flexlock-diff dirs results/run_a results/run_b --details # per-key differences
flexlock-diff dirs results/run_a results/run_b --format json
flexlock-diff db tasks.db <task_id1> <task_id2>
flexlock-diff mixed results/run_a tasks.db <task_id>
```

**Exit codes:** `0` match, `1` differ, `2` error — usable directly in scripts
and CI (older versions always exited 0).

---

## `flexlock-run` — Run Experiments

Complete reference for `flexlock-run` command-line interface.

## Basic Usage

```bash
flexlock-run [OPTIONS]
```

## Configuration Loading

### `--defaults`, `-d`
Load Python module containing default configuration.

**Accepted forms:**

| Form                                  | Resolves to                                |
|---------------------------------------|--------------------------------------------|
| `pkg.module.variable`                 | `from pkg.module import variable`          |
| `pkg.module:variable`                 | Same, with explicit colon split            |
| `path/to/file.py`                     | `defaults` variable in that file           |
| `path/to/file.py:variable`            | Named variable in that file                |

For the dotted form, the **last** component is the variable name and
everything before it is the module path. So `-d myconfig.defaults`
expects a module called `myconfig` containing a `defaults` attribute —
**not** `myconfig/defaults.py`. If your project layout is
`myconfig/defaults.py` with `defaults = {...}` inside, use
`-d myconfig.defaults.defaults` (or `-d myconfig/defaults.py`).

`flexlock-run` inserts the current working directory at the front of
`sys.path` for you, so dotted imports of packages in the project root
work without setting `PYTHONPATH=.`.

**Usage:**
```bash
flexlock-run -d myproject.config.defaults
flexlock-run -d configs/defaults.py
flexlock-run -d configs/experiments.py:hyperparam_grid
```

**Python module structure:**
```python
# myproject/config/defaults.py
from flexlock import py2cfg

def train(lr=0.01, epochs=10):
    pass

defaults = dict(
    train=py2cfg(train, lr=0.001),
    eval=py2cfg(evaluate)
)
```

---

### `--config`, `-c`
Load base YAML configuration file.

**Usage:**
```bash
flexlock-run -c config.yaml
```

**YAML structure:**
```yaml
_target_: myproject.train.train
lr: 0.01
epochs: 100
save_dir: outputs/run1
```

---

## Configuration Selection

### `--select`, `-s`
Select a specific node from the configuration tree.

**Usage:**
```bash
# Load defaults, then select 'train' node
flexlock-run -d myproject.defaults -s train

# Select nested node
flexlock-run -d myproject.defaults -s experiments.baseline

# Multi-stage: run several stages in order as a pipeline (space- or
# comma-separated). Each sweep item becomes one composite pipeline task.
flexlock-run -d myproject.defaults -s train linear_probe -o pipeline_dir=results/xp
flexlock-run -d myproject.defaults -s train,linear_probe \
    --sweep-target pipeline_dir --sweep results/xp1,results/xp2 --n_jobs 2
```

**Multi-stage (`-s` with more than one stage)** runs the stages sequentially as
a pipeline (a downstream stage sees the upstream stage's artifacts on disk). It
composes with `--sweep*`, `--slurm-config`/`--pbs-config`, and `--enqueue`:
each sweep item is merged into the root config before selection, then becomes
one composite `{_stages_: [...]}` task whose stages run in order on one worker,
while parallelism / array workers fan out across items. It is only incompatible
with `-O`/`-M` and `-e` (they target a single selected node). See usage guide
§14g. All stages of an item share one scheduler job (no per-stage HPC resources).

**Works with:**
- Python configs (dict keys)
- YAML configs (nested keys)

---

## Configuration Overrides

### `--overrides`, `-o`
Override keys in the **root** config (applied before `-s` selection).

Use `-o` for root-level anchors that downstream interpolations depend on (e.g.
`pipeline_dir`, `base_dir`). These values are frozen into the selected subtree
before execution, so interpolations like `${pipeline_dir}` in the stage config
resolve correctly.

> **When `-s` is used:** if a `-o` key also exists inside the selected node,
> flexlock will warn — your override landed on the root, not the stage. Use
> `-O` for those. Root-only anchors (`params`, `pipeline_dir`, …) are
> intentional and stay silent.

**Usage:**
```bash
# No selection — override lands directly
flexlock-run -d defaults -o lr=0.1

# With selection — override a root anchor that the subtree interpolates
flexlock-run -d defaults -s train -o pipeline_dir=results/run01

# Multiple root overrides
flexlock-run -d defaults -o base_dir=outputs seed=42
```

**Supports:**
- Primitive types: `param=1`, `flag=true`, `name=model`
- Nested paths: `model.layers=12`
- Lists: `devices=[0,1,2]`

---

### `--overrides-after-select`, `-O`
Override keys in the **selected** config node (applied after `-s` selection).

Use `-O` whenever you want to change a value that lives inside the selected
stage — `save_dir`, hyperparameters, datamodule settings, etc.

**Usage:**
```bash
# Select train node, then override its lr
flexlock-run -d defaults -s train -O lr=0.2

# Override save_dir of the selected stage
flexlock-run -d defaults -s train -O save_dir=results/my_run

# Combine root anchor (-o) with stage overrides (-O)
flexlock-run -d defaults -s train \
  -o pipeline_dir=results/run01 \   # root anchor frozen into subtree refs
  -O params.lr=5e-4 params.max_epochs=50  # stage-level overrides
```

---

## Parameter Sweeps

Run multiple experiments with different parameter values.

### Source Options (Mutually Exclusive)

#### `--sweep-key`
Use a key from the config containing a list of parameter sets.

**Usage:**
```bash
flexlock-run -d defaults --sweep-key param_grid
```

**Config example:**
```python
# defaults.py
config = dict(
    train=py2cfg(train),
    param_grid=[
        dict(lr=0.001, batch_size=32),
        dict(lr=0.01, batch_size=64),
        dict(lr=0.1, batch_size=128),
    ]
)
```

---

#### `--sweep-file`
Load sweep tasks from one or more files (YAML, JSON, or TXT). Pass multiple paths to concatenate them into a single sweep list.

**Usage:**
```bash
# Single YAML file with a list of override dicts
flexlock-run -d defaults --sweep-file sweep.yaml

# Multiple files — each file is loaded and results are concatenated
flexlock-run -d defaults --sweep-file exp1.yaml exp2.yaml exp3.yaml

# Text file with values (one per line)
flexlock-run -d defaults --sweep-file lr_values.txt --sweep-target lr
```

**File formats:**

**YAML/JSON — list of dicts** (multiple tasks per file):
```yaml
# sweep.yaml
- {lr: 0.001, batch_size: 32}
- {lr: 0.01, batch_size: 64}
- {lr: 0.1, batch_size: 128}
```

**YAML/JSON — single dict** (one task per file, useful with `--dump` or `--enqueue`):
```yaml
# exp1.yaml  (produced by: flexlock-run ... --dump > exp1.yaml)
lr: 0.001
batch_size: 32
```

**Text:** One value per line
```text
# lr_values.txt
0.001
0.01
0.1
```

**Multi-file behaviour:** A file containing a list contributes all its items; a file containing a single dict contributes one item. The results are concatenated in the order the files are listed.

---

#### `--sweep`
Provide comma-separated sweep values directly.

**Usage:**
```bash
# Simple values
flexlock-run -d defaults --sweep "0.001,0.01,0.1" --sweep-target lr

# Key=value pairs (creates dicts)
flexlock-run -d defaults --sweep "lr=0.001,lr=0.01,lr=0.1"
```

---

### Target

#### `--sweep-target`
Specify where to inject sweep values into the config.

**Usage:**
```bash
# Inject at root level (merges entire dict)
flexlock-run -d defaults --sweep-file sweep.yaml

# Inject at specific key (useful for simple values)
flexlock-run -d defaults --sweep "0.001,0.01,0.1" --sweep-target optimizer.lr
```

**Behavior:**
- **With `--sweep-target`:** Sweep values are set at the specified path
- **Without `--sweep-target`:** Sweep values (must be dicts) are merged at root

---

## Execution Control

### `--n_jobs`
Number of parallel workers for sweep execution.

**Usage:**
```bash
# Sequential execution (default)
flexlock-run -d defaults --sweep-file sweep.yaml --n_jobs 1

# Parallel execution (4 workers)
flexlock-run -d defaults --sweep-file sweep.yaml --n_jobs 4
```

**Notes:**
- `n_jobs=1`: Sequential execution
- `n_jobs>1`: Spawns multiprocessing workers (local)
- With HPC backends: Ignored (controlled by job array size)

---

### `--check-exists`
Skip execution if run with matching configuration already exists.

**Usage:**
```bash
flexlock-run -d defaults --check-exists
```

**Behavior:**
- Compares current config with existing `run.lock` files
- If match found: Skips execution
- If no match: Runs normally

---

### `--debug`
Enable debug mode with interactive post-mortem debugging.

**Usage:**
```bash
flexlock-run -d defaults --debug
```

**Sets:** `FLEXLOCK_DEBUG=true`

**Effects:**
- On exception: Drops into PDB debugger
- In notebooks: Injects local variables into global scope
- Useful for development and troubleshooting

---

### `--note`
Record a free-text intent as a top-level `note:` key in `run.lock` (sibling of
`timestamp`/`config`). The note **never enters the fingerprint**, so it can't
perturb caching or diffs. It surfaces in `flexlock show`/`graph`/`report`.

**Usage:**
```bash
flexlock-run -d defaults -s train --note "baseline before lr sweep"
```

For sweeps the note lands on the **master** `run.lock` only; sweep items inherit
it for display via their `.flexlock_marker` → master lookup. For a multi-stage
`-s a b` run, the same note is applied to each stage.

---

### `--dump`
Print the compiled configuration as clean YAML and exit — no decorative headers, no docstring. The output is machine-readable and can be redirected to a file for later use with `--sweep-file` or `--enqueue`.

**Usage:**
```bash
# Capture a compiled config to a file
flexlock-run -d defaults -s train --dump > experiments/base.yaml

# Capture several variants
flexlock-run -d defaults -s train -O lr=0.001 --dump > experiments/lr1e3.yaml
flexlock-run -d defaults -s train -O lr=0.01  --dump > experiments/lr1e2.yaml

# Later, run them as a sweep
flexlock-run -d defaults -s train \
  --sweep-file experiments/lr1e3.yaml experiments/lr1e2.yaml \
  --slurm-config slurm.yaml
```

**Notes:**
- `--dump` resolves interpolations lazily (uses `OmegaConf.to_yaml` without resolving), so `${vinc:}` paths remain in the output and fire correctly at run time.
- For human inspection with docstring output, use `--print-config` instead.

---

### `--enqueue`
Append the compiled configuration to a YAML queue file and exit without running. Creates the file if absent; subsequent calls append to it. The queue file is a plain YAML list and can be inspected, edited, or committed to version control.

**Usage:**
```bash
# Queue experiments one at a time (e.g. while a previous run is active)
flexlock-run -d defaults -s train -O lr=0.001 --enqueue queue.yaml
flexlock-run -d defaults -s train -O lr=0.01  --enqueue queue.yaml
flexlock-run -d defaults -s train -O lr=0.1   --enqueue queue.yaml

# Inspect the queue
cat queue.yaml

# Submit the whole queue
flexlock-run -d defaults -s train --sweep-file queue.yaml --slurm-config slurm.yaml
```

**Queue file format** (standard YAML list, one item per `--enqueue` call):
```yaml
- lr: 0.001
  save_dir: results/exp
- lr: 0.01
  save_dir: results/exp
- lr: 0.1
  save_dir: results/exp
```

**With a sweep** (`--sweep`/`--sweep-key`/`--sweep-file`), `--enqueue` appends
**one entry per sweep item** — each merged at `--sweep-target` and frozen —
instead of a single config. Previously the sweep was silently dropped.

**With multi-stage** (`-s` with more than one stage), `--enqueue` appends **one
composite `{_stages_: [...]}` entry per sweep item** (or one for a no-sweep
pipeline). Composite entries in a `--sweep-file` run as-is; plain entries in the
same file are merged into the compiled node config and run as single-stage
pipelines.

**Notes:**
- The enqueued config is stored with interpolations **unresolved** so that resolvers like `${vinc:}`/`${run_lock:}`/`${latest:}` fire at run time and each task gets its own unique directory.
- Writes are atomic (temp-file + rename) so concurrent `--enqueue` calls from different terminals are safe.
- Re-running `--sweep-file queue.yaml` after adding new items is safe: tasks already completed are skipped via the `INSERT OR IGNORE` logic in the task DB.

---

### `--print-config`
Print the fully compiled configuration and, if `_target_` is set, the target function's docstring, then exit without running.

**Usage:**
```bash
flexlock-run -d defaults -s train --print-config
flexlock-run -c config.yaml -O lr=0.1 --print-config
```

**Output example:**
```
=== COMPILED CONFIG ===
_target_: myproject.train.train
lr: 0.1
epochs: 100
save_dir: outputs/train

=== TARGET FUNCTION DOCSTRING ===
Target: myproject.train.train
Docstring:
    Train a model with the given configuration.
    ...
```

Useful for inspecting the final merged config before running, especially when many override layers are involved.

---

### `-h`, `--help`
Print the standard argument help followed by the compiled configuration (and target docstring if available), then exit. The config reflects all overrides provided on the command line.

**Usage:**
```bash
flexlock-run -d defaults -s train -O lr=0.1 --help
```

**Output:**
```
usage: flexlock-run [OPTIONS]
...

=== COMPILED CONFIG ===
_target_: myproject.train.train
lr: 0.1
...
```

---

## HPC Backend Configuration

Execute sweeps on HPC clusters using Slurm or PBS job schedulers.

### `--slurm-config`
Path to Slurm configuration YAML file.

**Usage:**
```bash
flexlock-run -d defaults --sweep-file sweep.yaml --slurm-config slurm.yaml
```

**Config file format:**
```yaml
# slurm.yaml
startup_lines:
  - "#SBATCH --job-name=flexlock_sweep"
  - "#SBATCH --cpus-per-task=4"
  - "#SBATCH --mem=16G"
  - "#SBATCH --time=01:00:00"
  - "#SBATCH --array=0-99"  # 100 workers
  - "module load python/3.10"
  - "source activate myenv"

# Optional: Custom Python executable
python_exe: "python"  # or "/path/to/venv/bin/python"

# Optional: Logging configuration
configure_logging: true
```

**Mutually exclusive with:** `--pbs-config`

---

### `--pbs-config`
Path to PBS configuration YAML file.

**Usage:**
```bash
flexlock-run -d defaults --sweep-file sweep.yaml --pbs-config pbs.yaml
```

**Config file format:**
```yaml
# pbs.yaml
startup_lines:
  - "#PBS -l select=1:ncpus=4:mem=16gb"
  - "#PBS -l walltime=01:00:00"
  - "#PBS -N flexlock_sweep"
  - "#PBS -J 0-99"  # 100 workers
  - "cd $PBS_O_WORKDIR"
  - "eval \"$(conda shell.bash hook)\""
  - "conda activate myenv"

# Optional: Custom Python executable (e.g., Singularity container)
python_exe: |
  singularity run
  --bind $(pwd):/workspace
  --pwd /workspace
  myenv.sif python

# Optional: Name configuration
configure_name: true
```

**Mutually exclusive with:** `--slurm-config`

> **Tip:** To run workers inside a Singularity/Docker container, set `python_exe` to the container invocation command (see the PBS example above). See [HPC Integration](./hpc_integration.md) for more details.

---

## Configuration Merging Order

Understanding the order in which configurations are merged:

```
1. Empty config
2. + @flexcli decorator defaults (if using decorator)
3. + Python defaults (--defaults)
4. + Base YAML (--config)
5. + Base merge (--merge)
6. + Base overrides (--overrides)
7. → SELECT node (--select)
8. + Inner merge (--merge-after-select)
9. + Inner overrides (--overrides-after-select)
10. → INJECT save_dir if missing
11. → EXECUTE or SWEEP
```

**Example:**
```bash
flexlock-run \
  -d myproject.defaults \      # Load defaults
  -o base_dir=outputs \         # Override at root
  -s train \                    # Select 'train' node
  -O lr=0.1 \                   # Override selected node
  --sweep "32,64,128" \         # Sweep batch sizes
  --sweep-target batch_size \   # Where to inject sweep
  --n_jobs 4                    # Parallel execution
```

**Resulting execution:**
- Loads `myproject.defaults`
- Sets `base_dir=outputs` at root
- Selects `train` config node
- Overrides `lr=0.1` in train config
- Runs 3 experiments with `batch_size=[32, 64, 128]`
- Uses 4 parallel workers

---

## Common Patterns

### Pattern 1: Simple Experiment
```bash
# -O because lr lives inside the train node (use -o only for root anchors)
flexlock-run -d myproject.defaults -s train -O lr=0.1
```

### Pattern 2: Hyperparameter Sweep
```bash
flexlock-run \
  -d myproject.defaults \
  --sweep "0.001,0.01,0.1" \
  --sweep-target optimizer.lr \
  --n_jobs 3
```

### Pattern 3: HPC Sweep with Slurm
```bash
flexlock-run \
  -d myproject.defaults \
  --sweep-file experiments.yaml \
  --slurm-config slurm.yaml
```

### Pattern 4: Containerized HPC
```bash
flexlock-run \
  -d myproject.defaults \
  --sweep-key param_grid \
  --pbs-config pbs_singularity.yaml
```

### Pattern 5: Debug Specific Config
```bash
flexlock-run \
  -d myproject.defaults \
  -s experiments.failing_exp \
  --debug
```

---

## Advanced Override Options

### `--merge`, `-m`
Merge a YAML/JSON file into the root config (before selection). Useful when you have a set of overrides stored in a file that apply at the top level.

```bash
flexlock-run -d defaults -m overrides.yaml
```

### `--merge-after-select`, `-M`
Merge a file into the selected config node (after selection). Useful for applying experiment-specific settings to an already-selected stage.

```bash
flexlock-run -d defaults -s train -M experiment1.yaml
```

These are file-based equivalents of `-o`/`-O`. Use them when overrides are too many to pass on the command line.

---

## See Also

- [Python API Reference](./python_api.md) - Programmatic usage with `Project` class
- [HPC Integration](./hpc_integration.md) - Detailed HPC setup guide
- [Debugging](./debugging.md) - Interactive debugging features
- [Reference](./reference.md) - Environment variables and exceptions
