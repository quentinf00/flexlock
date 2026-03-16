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

---

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

**Usage:**
```bash
flexlock-run -d myproject.config.defaults
```

**Python module structure:**
```python
# myproject/config/defaults.py
from flexlock import py2cfg

def train(lr=0.01, epochs=10):
    pass

config = dict(
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
```

**Works with:**
- Python configs (dict keys)
- YAML configs (nested keys)

---

## Configuration Overrides

### `--merge`, `-m`
Merge a YAML/JSON file into the root config (before selection).

**Usage:**
```bash
flexlock-run -d defaults -m overrides.yaml
```

**Override file example:**
```yaml
lr: 0.1
batch_size: 64
```

---

### `--overrides`, `-o`
Override specific keys in root config using dot-notation (before selection).

**Usage:**
```bash
# Single override
flexlock-run -d defaults -o lr=0.1

# Multiple overrides
flexlock-run -d defaults -o lr=0.1 epochs=100 batch_size=32

# Nested overrides
flexlock-run -d defaults -o optimizer.lr=0.1 optimizer.momentum=0.9
```

**Supports:**
- Primitive types: `param=1`, `flag=true`, `name=model`
- Nested paths: `model.layers=12`
- Lists: `devices=[0,1,2]`

---

### `--merge-after-select`, `-M`
Merge a file into the selected config node (after selection).

**Usage:**
```bash
# Select train node, then merge experiment-specific settings
flexlock-run -d defaults -s train -M experiment1.yaml
```

---

### `--overrides-after-select`, `-O`
Override keys in selected config node (after selection).

**Usage:**
```bash
# Select train, then override its lr parameter
flexlock-run -d defaults -s train -O lr=0.2

# Useful for modifying nested configs without affecting root
flexlock-run -d defaults -s experiments.exp1 -O model.depth=50
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
Load sweep values from a file (YAML, JSON, or TXT).

**Usage:**
```bash
# YAML file with list of configs
flexlock-run -d defaults --sweep-file sweep.yaml

# Text file with values (one per line)
flexlock-run -d defaults --sweep-file lr_values.txt --sweep-target lr
```

**File formats:**

**YAML/JSON:** List of dicts
```yaml
# sweep.yaml
- {lr: 0.001, batch_size: 32}
- {lr: 0.01, batch_size: 64}
- {lr: 0.1, batch_size: 128}
```

**Text:** One value per line
```text
# lr_values.txt
0.001
0.01
0.1
```

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

---

### Containerized Execution

Run workers in Singularity/Docker containers by specifying custom `python_exe`:

```yaml
# pbs_singularity.yaml
startup_lines:
  - "#PBS -l select=1:ncpus=4"
  - "cd $PBS_O_WORKDIR"

python_exe: >-
  singularity run
  --bind $(pwd)/src:/app/src
  --bind $(pwd)/outputs:/workspace/outputs
  --pwd /workspace
  myenv.sif python
```

**Usage:**
```bash
flexlock-run -d defaults --sweep-file sweep.yaml --pbs-config pbs_singularity.yaml
```

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
flexlock-run -d myproject.defaults -s train -o lr=0.1
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

## See Also

- [Python API Reference](./python_api.md) - Programmatic usage with `Project` class
- [HPC Integration](./hpc_integration.md) - Detailed HPC setup guide
- [Debugging](./debugging.md) - Interactive debugging features
- [Reference](./reference.md) - Environment variables and exceptions
