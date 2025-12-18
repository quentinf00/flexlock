# Example 02: The "Scientist" (Reproducibility & Lineage)

This example demonstrates FlexLock's reproducibility features for ensuring experiments can be precisely recreated and validated.

## What You'll Learn

- Automatic snapshot generation with `snapshot_config`
- Git state tracking (commit hash + tree hash)
- Data hash computation for provenance
- Using `flexlock-diff` to compare experiments
- Detecting changes in code, data, or configuration

## Files

- `train_model.py` - Training script with snapshot tracking
- `data/train.csv` - Example training dataset
- `README.md` - This file

## Key Concept: The Run Lock File

FlexLock creates a `run.lock` file that captures:
- **Configuration**: All parameters used
- **Git State**: Commit hash, branch, and tree hash (content fingerprint)
- **Data Hashes**: Content-based hash of input data
- **Timestamp**: When the experiment ran
- **Environment**: Python version, dependencies
- **Lineage**: Links to upstream experiments (automatic tracking)

This allows you to:
1. Reproduce experiments exactly
2. Verify that results match
3. Track lineage in multi-stage pipelines

## Configuring Snapshot Tracking

FlexLock needs to know **what to track**. You configure this using the `_snapshot_` field in your configuration:

### Basic Configuration

```python
from flexlock import flexcli

@flexcli
def train(
    data_path: str = "data/train.csv",
    lr: float = 0.01,
    save_dir: str = "${vinc:results/train}",
    _snapshot_: dict = {
        "repos": {"main": "."},  # Track git repo at current directory
        "data": {"train": "${...data_path}"}  # Track data file
    }
):
    # Your training code
    pass
```

### Configuration Fields

#### 1. **repos** (Git Tracking)

Specifies which git repositories to track:

```python
_snapshot_ = {
    "repos": {
        "main": ".",  # Track current directory
        "lib": "../my-library",  # Track another repo
    }
}
```

FlexLock records:
- **Commit hash**: The git commit
- **Tree hash**: Content fingerprint (changes even if commit doesn't)
- **Branch**: Current branch name
- **Is dirty**: Whether there are uncommitted changes

#### 2. **data** (Data Tracking)

Specifies which data files/directories to hash:

```python
_snapshot_ = {
    "data": {
        "train": "${...data_path}",  # Use interpolation
        "val": "data/val.csv",  # Or hardcode path
        "test": "${...test_path}"
    }
}
```

FlexLock computes content hashes to detect data changes.

#### 3. **prevs** (Lineage Tracking)

Explicitly specify upstream dependencies:

```python
_snapshot_ = {
    "prevs": [
        "${...preprocessed_dir}",  # Track output from previous stage
    ]
}
```

**Automatic Lineage Discovery**: FlexLock also automatically discovers lineage by:
- Scanning paths in your config for `run.lock` files
- Following the dependency chain backwards
- Recording the full experiment DAG

### Example: Multi-Stage Pipeline

```python
# Stage 1: Preprocess
@flexcli
def preprocess(
    input_data: str = "data/raw/",
    output_dir: str = "${vinc:results/preprocess}",
    _snapshot_: dict = {
        "repos": {"main": "."},
        "data": {"raw_data": "${...input_data}"}
    }
):
    # Preprocessing logic
    return {"output_dir": output_dir}

# Stage 2: Train (depends on preprocess)
@flexcli
def train(
    data_dir: str = "results/preprocess/run_0001",  # From stage 1
    lr: float = 0.01,
    save_dir: str = "${vinc:results/train}",
    _snapshot_: dict = {
        "repos": {"main": "."},
        "data": {},  # No new data inputs
        "prevs": ["${...data_dir}"]  # Track dependency on preprocess
    }
):
    # Training logic - FlexLock automatically discovers the preprocess run.lock
    pass
```

### Why Explicit Configuration?

FlexLock requires explicit configuration because:

1. **Selective Tracking**: Not all files need tracking (e.g., temporary files)
2. **Performance**: Hashing large datasets takes time
3. **Flexibility**: Different experiments need different tracking levels
4. **Clarity**: Makes dependencies explicit in code

### Tips for Configuration

**Do:**
- ✅ Track source code repos with `repos`
- ✅ Track input data files/directories with `data`
- ✅ Use `${...variable}` interpolation for dynamic paths
- ✅ Track upstream stage outputs with `prevs` or automatic discovery

**Don't:**
- ❌ Track output directories (they'll differ between runs)
- ❌ Track temp files or caches
- ❌ Track system directories

## Prerequisites

```bash
# Install FlexLock
pip install flexlock
# or
conda install -c quentinf00 flexlock
```

## Demo Scenarios

### Scenario 1: Generate Snapshot

Run the training script to create a snapshot:

```bash
python train_model.py
```

**What happens:**
1. Training runs with default parameters
2. Reads data from `data/train.csv`
3. Creates `results/reproducibility_XXXX/` directory
4. Saves:
   - `run.lock` - Full snapshot
   - `config.yaml` - Configuration used
   - `training.log` - Execution log
   - `model.txt` - Model parameters
   - `results.txt` - Training results

**Inspect the snapshot:**
```bash
# View the snapshot
cat results/reproducibility_0001/run.lock
```

You'll see:
```yaml
timestamp: "2025-12-16 15:30:00"
config:
  data_path: 02_reproducibility/data/train.csv
  model_type: linear
  learning_rate: 0.01
  # ... other config

repos:
  ".":
    commit: abc123...
    branch: main
    tree_hash: def456...  # Content fingerprint
    is_dirty: false

data:
  train_data: xyz789...  # Hash of train.csv
```

### Scenario 2: Verify Identical Runs

Run the same command again:

```bash
python train_model.py
```

Now compare the two runs:

```bash
# List your results
ls results/

# Compare the two snapshots
flexlock-diff dirs results/reproducibility_0001 results/reproducibility_0002
```

**Expected output:**
```
=== Snapshot Comparison ===

Git:    ✓ Match
Config: ✓ Match
Data:   ✓ Match

Overall: ✓ Snapshots Match
```

**Why they match:**
- Same code (git tree hash identical)
- Same configuration
- Same input data (hash unchanged)

### Scenario 3: Detect Code Changes

Modify the training script (e.g., add a comment or change a print statement):

```bash
# Edit the file
echo "# Test comment" >> train_model.py

# Run again
python train_model.py

# Compare with baseline
flexlock-diff dirs results/reproducibility_0001 results/reproducibility_0003
```

**Expected output:**
```
=== Snapshot Comparison ===

Git:    ✗ Differ
  - tree_hash: def456... → ghi789...
Config: ✓ Match
Data:   ✓ Match

Overall: ✗ Snapshots Differ
```

**What this tells you:**
- Code changed (different git tree hash)
- Parameters unchanged
- Data unchanged
- Results may differ due to code change

**Undo the change:**
```bash
git checkout train_model.py
```

### Scenario 4: Detect Data Changes

Modify the input data:

```bash
# Change one value in the CSV
sed -i 's/0.5,0.3,0.8,1/0.9,0.3,0.8,1/' data/train.csv

# Run again
python train_model.py

# Compare
flexlock-diff dirs results/reproducibility_0001 results/reproducibility_0004
```

**Expected output:**
```
=== Snapshot Comparison ===

Git:    ✓ Match
Config: ✓ Match
Data:   ✗ Differ
  - train_data: xyz789... → abc123...

Overall: ✗ Snapshots Differ
```

**What this tells you:**
- Code unchanged
- Parameters unchanged
- **Data changed** (different hash)
- Results differ because input data is different

**Undo the change:**
```bash
git checkout data/train.csv
```

### Scenario 5: Parameter Changes

Run with different parameters:

```bash
python train_model.py -o learning_rate=0.05 max_iter=200

# Compare to baseline
flexlock-diff dirs results/reproducibility_0001 results/reproducibility_0005
```

**Expected output:**
```
=== Snapshot Comparison ===

Git:    ✓ Match
Config: ✗ Differ
  - config.learning_rate: 0.01 → 0.05
  - config.max_iter: 100 → 200
Data:   ✓ Match

Overall: ✗ Snapshots Differ
```

## Advanced Usage

### Custom Data Path

Use your own data:

```bash
python train_model.py -o data_path=data/my_data.csv
```

**Note:** FlexLock will automatically compute and track the hash of `my_data.csv`.

### Detailed Diff

Get detailed information about differences:

```bash
flexlock-diff dirs results/reproducibility_0001 results/reproducibility_0002 --details
```

Shows:
- Exact config parameters that changed
- Which files have different hashes
- Git commit differences

### CI/CD Integration

Use in continuous integration:

```bash
#!/bin/bash
# test_reproducibility.sh

# Run experiment
python train_model.py

# Run again (should be identical)
python train_model.py

# Verify reproducibility
flexlock-diff dirs results/reproducibility_0001 results/reproducibility_0002

if [ $? -eq 0 ]; then
    echo "✓ Reproducibility verified"
    exit 0
else
    echo "✗ Results not reproducible"
    exit 1
fi
```

## Understanding snapshot_config

The `@flexcli` decorator accepts a `snapshot_config` parameter:

```python
@flexcli(
    snapshot_config={
        "repos": ["."],                          # Track git state
        "data": {"train_data": "${data_path}"},  # Track data hash
    }
)
```

**What it does:**
- `repos`: List of git repositories to track (paths relative to working directory)
- `data`: Dictionary mapping names to data paths
  - Supports OmegaConf interpolation (e.g., `"${data_path}"`)
  - Computes hash of each data source
  - Tracks in `run.lock`

**Without snapshot_config:**
- No automatic snapshot creation
- You must call `snapshot()` manually

**With snapshot_config:**
- Automatic snapshot after function execution
- Cleaner code (no manual snapshot calls)
- Consistent tracking across experiments

## How Data Hashing Works

FlexLock uses **content-based hashing**:

1. **Files**: Computes xxHash128 of file contents
   - Ignores timestamps and permissions
   - Only content matters

2. **Directories**: Recursively hashes all files
   - Deterministic tree hashing
   - Cached for performance

3. **Cache**: Hashes stored in `~/.cache/flexlock/hashes.db`
   - First hash may be slow
   - Subsequent hashes are instant (if file unchanged)

**Example:**
```bash
# First run: computes hash
python train_model.py  # Takes 0.5s

# Second run: uses cache
python train_model.py  # Takes 0.01s (50x faster!)
```

## Common Workflows

### 1. Experiment Tracking

```bash
# Run experiment
python train_model.py -o model_type=linear learning_rate=0.01

# Archive the snapshot
cp results/reproducibility_0001/run.lock experiments/baseline.lock

# Later: verify reproducibility
python train_model.py -o model_type=linear learning_rate=0.01
flexlock-diff dirs experiments/baseline.lock results/reproducibility_0002/
```

### 2. Multi-Person Collaboration

**Person A:**
```bash
# Run experiment
python train_model.py

# Commit snapshot to git
git add results/reproducibility_0001/run.lock
git commit -m "Baseline results"
git push
```

**Person B:**
```bash
# Pull changes
git pull

# Try to reproduce
python train_model.py

# Verify match
flexlock-diff dirs results/reproducibility_0001 results/reproducibility_0002
```

### 3. Debugging Discrepancies

If two runs give different results:

```bash
# Compare snapshots
flexlock-diff dirs run_a/ run_b/ --details
```

Check each section:
- **Git differs** → Code changed
- **Config differs** → Parameters changed
- **Data differs** → Input data changed

## Troubleshooting

### "Data file not found"

Make sure you're running from the project root:
```bash
cd /path/to/my_awesome_project
python 02_reproducibility/train_model.py
```

Or use absolute path:
```bash
python train_model.py -o data_path=/absolute/path/to/data.csv
```

### Git tree hash differs but code unchanged

This can happen if:
- You have untracked files
- Your `.gitignore` changed
- You're on a different branch

Check git status:
```bash
git status
```

### Diff shows "Config differs" on save_dir

This is expected! The `save_dir` includes `${vinc:}` which auto-increments.

FlexLock automatically ignores `save_dir` and `timestamp` when comparing configs.

## Next Steps

Try these exercises:

1. **Create custom data**: Generate your own `data/custom.csv` and run with it
2. **Test dirty git state**: Make uncommitted changes and see how FlexLock tracks them
3. **Build a pipeline**: Use this as stage 1, create a stage 2 that loads the model

## Related Examples

- **01_basics**: Learn about CLI and sweeps
- **03_yaml_config**: Advanced configuration management
- **05_pipeline**: Multi-stage workflows with lineage

## Additional Resources

- [Snapshot Documentation](../../flexlock/docs/snapshot.md)
- [Data Hashing System](../../flexlock/docs/snapshot.md#data-hashing-system)
- [CLI Tools (flexlock-diff)](../../flexlock/docs/cli_tools.md)
