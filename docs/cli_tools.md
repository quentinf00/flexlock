# Command-Line Tools

FlexLock provides utility CLI tools for working with snapshots and experiment data. These tools help you compare runs, verify reproducibility, and manage experiment results.

**Available CLI Tools:**
- **`flexlock-run`**: Standalone runner for executing experiments directly from config files ([see FlexLockRunner docs](./runner.md#standalone-cli-flexlock-run))
- **`flexlock-diff`**: Compare snapshots for reproducibility verification
- **`flexlock-export`**: Extract task snapshots from databases to files

This document covers the utility tools (`flexlock-diff` and `flexlock-export`). For `flexlock-run`, see the [FlexLockRunner documentation](./runner.md).

---

## Installation Verification

After installing FlexLock, verify that the CLI tools are available:

```bash
flexlock-diff --help
flexlock-export --help
```

If you get a "command not found" error, see the [Installation Troubleshooting](./installation.md#troubleshooting) guide.

---

## flexlock-diff: Compare Snapshots

Compare snapshots from different sources to verify reproducibility and debug discrepancies.

### Purpose

The `flexlock-diff` tool compares two FlexLock snapshots and reports differences in:
- **Git repositories**: Commits, branches, and tree hashes
- **Configuration**: All configuration parameters
- **Data**: File hashes and data dependencies

### Basic Usage

```bash
flexlock-diff <mode> <source1> <source2> [--details]
```

**Modes:**
- `dirs`: Compare two directory-based snapshots
- `db`: Compare two database-based snapshots
- `mixed`: Compare directory snapshot to database snapshot

---

### Mode 1: Comparing Two Directories

Compare `run.lock` files from two experiment directories:

```bash
flexlock-diff dirs results/exp_0001 results/exp_0002
```

**Output:**
```
=== Snapshot Comparison ===

Git:    ✓ Match
Config: ✗ Differ
Data:   ✓ Match

Overall: ✗ Snapshots Differ
```

**Show Detailed Differences:**

```bash
flexlock-diff dirs results/exp_0001 results/exp_0002 --details
```

**Output with details:**
```
=== Snapshot Comparison ===

Git:    ✓ Match

Config: ✗ Differ
  - config.param: 10 → 20
  - config.learning_rate: 0.001 → 0.01

Data:   ✓ Match

Overall: ✗ Snapshots Differ
```

**Use Cases:**
- Compare two experimental runs
- Verify parameter changes between experiments
- Debug unexpected differences in results

---

### Mode 2: Comparing Tasks in Database

Compare two tasks stored in a FlexLock task database (from parallel sweeps):

```bash
flexlock-diff db results/sweep/run.lock.tasks.db abc123def456 def789ghi012
```

**Arguments:**
- `db_path`: Path to the task database
- `task_hash_1`: First task hash to compare
- `task_hash_2`: Second task hash to compare

**Output:**
```
=== Snapshot Comparison ===

Git:    ✓ Match (both reference same master snapshot)
Config: ✗ Differ
  - config.learning_rate: 0.001 → 0.01
Data:   ✓ Match

Overall: ✗ Snapshots Differ
```

**Use Cases:**
- Compare tasks within a parameter sweep
- Identify which parameters varied between tasks
- Debug task-specific issues

---

### Mode 3: Comparing Directory to Database Task

Mix directory and database sources:

```bash
flexlock-diff mixed results/exp_0001 results/sweep/run.lock.tasks.db abc123def456
```

**Arguments:**
- `dir_path`: Path to directory with `run.lock`
- `db_path`: Path to task database
- `task_hash`: Task hash in database to compare

**Use Cases:**
- Compare a standalone run to a task in a sweep
- Verify sweep task matches expected baseline
- Cross-check results between different execution modes

**Add --details for more information:**

```bash
flexlock-diff mixed results/exp_0001 results/sweep/run.lock.tasks.db abc123def456 --details
```

---

### Exit Codes

`flexlock-diff` returns different exit codes for automation:

| Exit Code | Meaning | Description |
|-----------|---------|-------------|
| `0` | Match | Snapshots are identical |
| `1` | Differ | Snapshots have differences |
| `2` | Error | Comparison failed (missing files, invalid format, etc.) |

### Example: CI/CD Integration

```bash
#!/bin/bash
# ci_reproducibility_check.sh

# Run experiment
python train.py --config baseline.yml

# Compare to reference snapshot
flexlock-diff dirs reference_run/ results/latest/

if [ $? -eq 0 ]; then
    echo "✓ Reproducibility verified"
    exit 0
elif [ $? -eq 1 ]; then
    echo "✗ Results differ from reference"
    flexlock-diff dirs reference_run/ results/latest/ --details
    exit 1
else
    echo "✗ Comparison failed"
    exit 2
fi
```

---

### What Gets Compared

#### 1. Git Section
Compares repository state:
- Commit hashes
- Branch names
- Tree hashes (content fingerprints)
- Dirty state indicators

**Note:** Minor differences like branch names may not indicate actual code differences if tree hashes match.

#### 2. Config Section
Compares all configuration parameters:
- Model hyperparameters
- Training settings
- Data paths
- All custom configuration fields

**Automatically ignores:**
- `save_dir` (expected to differ)
- `timestamp` (always different)
- Other fields marked as non-deterministic

#### 3. Data Section
Compares data hashes:
- Input data files
- Preprocessing artifacts
- Any tracked data dependencies

**Match criteria:** Hashes must be identical.

---

### Common Use Cases

#### Verify Reproducibility

```bash
# Run baseline
python experiment.py --seed 42

# Save as reference
cp -r results/exp_0005 reference/

# Later: verify reproducibility
python experiment.py --seed 42
flexlock-diff dirs reference/ results/exp_0010

# Expected: Git ✓, Config ✓, Data ✓
```

#### Debug Discrepancies

```bash
# Why do these runs give different results?
flexlock-diff dirs results/run_A results/run_B --details

# Output shows:
# Config: ✗ Differ
#   - config.batch_size: 32 → 64  ← Found the culprit!
```

#### Validate Sweep Tasks

```bash
# Verify all tasks in sweep use same code
flexlock-diff db results/sweep/run.lock.tasks.db task1 task2

# Expected: Git ✓, Config ✗ (params differ), Data ✓
```

---

## flexlock-export: Extract Snapshots

Export task snapshots from databases to standalone directories for analysis, archival, or sharing.

### Purpose

The `flexlock-export` tool extracts snapshots from FlexLock task databases (created during parallel sweeps) and saves them as traditional `run.lock` files in directories.

**Why use this:**
- Archive results before cleaning up databases
- Extract specific tasks for detailed analysis
- Share task snapshots with collaborators
- Post-process sweep results with standard tools

### Basic Usage

```bash
flexlock-export --db <database_path> [options]
```

---

### Export Single Task

Extract a specific task by its hash:

```bash
flexlock-export \
  --db results/sweep/run.lock.tasks.db \
  --task abc123def456 \
  --out exported/task_001
```

**Result:**
Creates `exported/task_001/run.lock` with the full snapshot.

**Directory structure:**
```
exported/task_001/
└── run.lock          # Complete snapshot for this task
```

---

### Export All Tasks

Export all tasks from a database to individual directories:

```bash
flexlock-export \
  --db results/sweep/run.lock.tasks.db \
  --out exported/all_tasks
```

**Result:**
```
exported/all_tasks/
├── task_abc123de/
│   └── run.lock
├── task_def456gh/
│   └── run.lock
├── task_ghi789jk/
│   └── run.lock
└── ...
```

Each task is exported to a subdirectory named `task_<hash_prefix>/`.

---

### Filter by Status

Export only tasks with specific status:

```bash
# Export only completed tasks
flexlock-export \
  --db results/sweep/run.lock.tasks.db \
  --out exported/completed \
  --status done

# Export failed tasks for debugging
flexlock-export \
  --db results/sweep/run.lock.tasks.db \
  --out exported/failed \
  --status failed

# Export pending tasks
flexlock-export \
  --db results/sweep/run.lock.tasks.db \
  --out exported/pending \
  --status pending
```

**Available Statuses:**
- `pending`: Not yet started
- `running`: Currently executing
- `done`: Successfully completed
- `failed`: Execution failed with error

---

### Finding Task IDs

If you don't know the task hashes, you can query the database:

#### Option 1: Using sqlite3

```bash
# List all task hashes
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT task_hash, status FROM tasks;"

# List completed tasks only
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT task_hash, status FROM tasks WHERE status='done';"

# Count tasks by status
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT status, COUNT(*) FROM tasks GROUP BY status;"
```

#### Option 2: Export all and inspect

```bash
# Export everything to temporary directory
flexlock-export --db results/sweep/run.lock.tasks.db --out temp_export

# Browse exported tasks
ls temp_export/
# task_abc123de/  task_def456gh/  task_ghi789jk/  ...
```

---

### Task Database Location

Task databases are automatically created during parallel sweeps at:

```
<save_dir>/run.lock.tasks.db
```

**Example:**
```yaml
# config.yml
save_dir: results/hp_sweep
```

After running a sweep:
```bash
python train.py --config config.yml --sweep-file sweep.yaml --n_jobs 4
```

Database location:
```
results/hp_sweep/run.lock.tasks.db
```

---

### Use Cases

#### 1. Post-Processing Analysis

```bash
# Export all completed tasks
flexlock-export \
  --db results/sweep/run.lock.tasks.db \
  --out analysis/tasks \
  --status done

# Analyze results
for task_dir in analysis/tasks/task_*/; do
    python analyze_results.py "$task_dir"
done
```

#### 2. Archival

```bash
# Export sweep results before cleanup
flexlock-export \
  --db results/old_sweep/run.lock.tasks.db \
  --out archive/experiment_2025_12_16

# Compress for storage
tar -czf archive_exp.tar.gz archive/experiment_2025_12_16/

# Safe to delete database now
rm -rf results/old_sweep/
```

#### 3. Debugging Failed Tasks

```bash
# Export only failed tasks
flexlock-export \
  --db results/sweep/run.lock.tasks.db \
  --out debug/failed \
  --status failed

# Inspect configurations
cat debug/failed/task_abc123de/run.lock

# Try to reproduce failure
python reproduce.py --config debug/failed/task_abc123de/run.lock
```

#### 4. Sharing Results

```bash
# Export specific interesting task
flexlock-export \
  --db results/sweep/run.lock.tasks.db \
  --task best_performing_task_hash \
  --out share/best_result

# Share with collaborator
zip -r best_result.zip share/best_result/
# Send best_result.zip
```

---

## Tips and Tricks

### Scripting with CLI Tools

Combine `flexlock-diff` and `flexlock-export` for powerful workflows:

```bash
#!/bin/bash
# compare_sweep_to_baseline.sh

BASELINE="reference/baseline"
SWEEP_DB="results/sweep/run.lock.tasks.db"
EXPORT_DIR="exported"

# Export all completed tasks
flexlock-export --db "$SWEEP_DB" --out "$EXPORT_DIR" --status done

# Compare each to baseline
echo "Comparing tasks to baseline..."
for task_dir in "$EXPORT_DIR"/task_*/; do
    task_name=$(basename "$task_dir")
    echo "Checking $task_name..."

    if flexlock-diff dirs "$BASELINE" "$task_dir" > /dev/null 2>&1; then
        echo "  ✓ $task_name matches baseline"
    else
        echo "  ✗ $task_name differs from baseline"
        flexlock-diff dirs "$BASELINE" "$task_dir" --details | grep "config\."
    fi
done
```

### Integration with Version Control

Track reference snapshots in git for reproducibility:

```bash
# Export reference snapshot
flexlock-export \
  --db results/final_sweep/run.lock.tasks.db \
  --task final_model_task_hash \
  --out reference/final_model

# Add to version control
git add reference/final_model/run.lock
git commit -m "Add reference snapshot for final model"

# Team members can verify reproducibility
python train.py --config final_config.yml
flexlock-diff dirs reference/final_model/ results/reproduced_run/
```

### Batch Comparison

Compare all tasks in a sweep to each other:

```bash
#!/bin/bash
# find_outliers.sh

DB="results/sweep/run.lock.tasks.db"
EXPORT="exported_sweep"

# Export all tasks
flexlock-export --db "$DB" --out "$EXPORT"

# Find first task as reference
REFERENCE=$(ls -d "$EXPORT"/task_* | head -n 1)

echo "Reference: $REFERENCE"
echo "Comparing all tasks to reference..."

for task_dir in "$EXPORT"/task_*/; do
    if [ "$task_dir" != "$REFERENCE" ]; then
        if ! flexlock-diff dirs "$REFERENCE" "$task_dir" > /dev/null 2>&1; then
            echo "Task $(basename $task_dir) differs from reference"
        fi
    fi
done
```

### Automated Reproducibility Testing

Add to your CI/CD pipeline:

```bash
# .github/workflows/reproducibility.yml
name: Reproducibility Test

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install FlexLock
        run: |
          conda install -c quentinf00 flexlock

      - name: Run experiment
        run: python experiment.py --config baseline.yml

      - name: Verify reproducibility
        run: |
          flexlock-diff dirs reference/ results/latest/
          if [ $? -ne 0 ]; then
            echo "Reproducibility test failed"
            flexlock-diff dirs reference/ results/latest/ --details
            exit 1
          fi
```

---

## Troubleshooting

### "command not found: flexlock-diff"

The CLI tools are installed as console entry points. If they're not found:

1. **Check installation:**
   ```bash
   python -c "import flexlock; print(flexlock.__file__)"
   ```

2. **Verify PATH:**
   ```bash
   # For conda
   echo $CONDA_PREFIX/bin

   # Add to PATH if needed
   export PATH="$CONDA_PREFIX/bin:$PATH"
   ```

3. **Reinstall if needed:**
   ```bash
   conda install -c quentinf00 flexlock --force-reinstall
   ```

### "No such file or directory: run.lock"

Ensure the directories contain `run.lock` files:

```bash
# Check for run.lock
ls results/exp_0001/run.lock

# If missing, the experiment may not have created a snapshot
# Add snapshot() call to your script
```

### "Task hash not found in database"

Verify the task hash exists:

```bash
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT task_hash FROM tasks WHERE task_hash LIKE 'abc%';"
```

Use the correct full hash or export all tasks to find it.

### Comparison shows unexpected differences

If Git sections differ but shouldn't:

```bash
# Use --details to see what differs
flexlock-diff dirs run1/ run2/ --details

# Common non-issues:
# - Different branch names (same tree hash = same code)
# - timestamp differences (expected)
# - save_dir differences (expected)
```

---

## Summary

FlexLock provides three essential CLI tools:

| Tool | Purpose | Key Features |
|------|---------|--------------|
| `flexlock-run` | Run experiments | Direct config execution, sweeps, no Python script needed ([docs](./runner.md)) |
| `flexlock-diff` | Compare snapshots | 3 modes (dirs/db/mixed), exit codes for CI/CD, detailed diff output |
| `flexlock-export` | Extract from database | Export single/all/filtered tasks, status filtering, archival-ready |

**Typical Workflows:**

1. **Quick experiments**: Run configs directly with `flexlock-run --config exp.yml`
2. **Verify reproducibility**: Run experiment → Compare with `flexlock-diff`
3. **Debug discrepancies**: Use `--details` flag to identify differences
4. **Archive sweep results**: Export with `flexlock-export` → Compress → Store
5. **Post-process sweeps**: Export filtered tasks → Batch analysis
6. **CI/CD integration**: Automated reproducibility checks using exit codes

These tools make FlexLock's features accessible from the command line, enabling powerful automation and analysis workflows without requiring Python scripts.
