# Example 01: The "Script" (Basics)

This example demonstrates the fundamental features of FlexLock's `@flexcli` decorator for creating command-line interfaces from Python functions.

## What You'll Learn

- Using `@flexcli` to create instant CLIs
- Overriding parameters from command line
- Running parameter sweeps (CLI and file-based)
- Automatic result tracking and reproducibility

## Files

- `simple_script.py` - Main script with training function
- `grids.yaml` - Example sweep configurations
- `README.md` - This file

## Prerequisites

```bash
# Install FlexLock
pip install flexlock
# or
conda install -c quentinf00 flexlock
```

## Demo Scenarios

### 1. Default Run

Run with default parameters:

```bash
python simple_script.py
```

**Expected output:**
- Training runs with `lr=0.01`, `batch_size=32`, `epochs=10`
- Results saved to `results/basics/` with automatic versioning
- Creates `run.lock` snapshot for reproducibility

### 2. Parameter Override

Override parameters from command line:

```bash
python simple_script.py -o lr=0.1
```

**Expected output:**
- Training runs with `lr=0.1` (overridden)
- Other parameters use defaults
- New result directory created

**Multiple overrides:**
```bash
python simple_script.py -o lr=0.05 batch_size=64 epochs=20
```

### 3. CLI Sweep

Run multiple experiments with different learning rates:

```bash
python simple_script.py --sweep "0.001,0.01,0.1" --sweep-target lr --n_jobs 3
```

**Expected output:**
- Runs 3 experiments in parallel (one for each learning rate)
- Each experiment gets its own result directory
- Task database created at `results/basics/run.lock.tasks.db`

**What happens:**
1. FlexLock creates a task queue with 3 configurations
2. Spawns 3 parallel workers (or uses cluster if configured)
3. Each worker processes one configuration
4. All results tracked in task database

### 4. File-Based Sweep

Run a more complex sweep from a YAML file:

```bash
python simple_script.py --sweep-file grids.yaml --n_jobs 2
```

**Expected output:**
- Runs 6 experiments (defined in `grids.yaml`)
- 2 experiments run in parallel at a time
- Results organized in sweep directory

**Inspect results:**
```bash
# View sweep status
sqlite3 results/basics/run.lock.tasks.db \
  "SELECT status, COUNT(*) FROM tasks GROUP BY status;"

# Export results
flexlock-export --db results/basics/run.lock.tasks.db --out results/exported/
```

## Understanding the Output

After running, you'll find:

```
results/basics/
├── run.lock              # Master snapshot (for sweeps)
├── run.lock.tasks.db     # Task database (for sweeps)
├── config.yaml           # Resolved configuration
└── results.txt           # Training results
```

For single runs:
```
results/basics/
├── run.lock              # Snapshot of this run
├── config.yaml           # Configuration used
└── results.txt           # Training results
```

## Key Features Demonstrated

### @flexcli Decorator

```python
@flexcli(default_config=Config)
def train(cfg: Config):
    # Your code here
```

**What it provides:**
- Automatic CLI argument parsing
- Configuration management
- Parameter override support
- Sweep execution
- Result tracking

### Configuration Class

```python
class Config:
    lr: float = 0.01
    batch_size: int = 32
    epochs: int = 10
    save_dir: str = "results/basics/${vinc:}"
```

**Features:**
- Type hints for documentation
- Default values
- OmegaConf resolvers (like `${vinc:}` for auto-versioning)

### Snapshot Function

```python
snapshot(cfg, repos=["."], snapshot_path=output_dir / "run.lock")
```

**Captures:**
- Configuration used
- Git commit hash
- Timestamp
- Environment info

## Next Steps

Try these exercises:

1. **Modify the script**: Add a new parameter (e.g., `momentum: float = 0.9`)
2. **Create your own sweep**: Edit `grids.yaml` to test different combinations
3. **Verify reproducibility**: Run the same config twice and use `flexlock-diff` to compare

## Troubleshooting

### "Command not found: python"

Try `python3` instead of `python`.

### Sweep runs sequentially instead of in parallel

Check that `--n_jobs` is set > 1:
```bash
python simple_script.py --sweep-file grids.yaml --n_jobs 4
```

### Results overwrite each other

Make sure your `save_dir` includes `${vinc:}` for auto-versioning:
```python
save_dir: str = "results/basics/${vinc:}"
```

## Related Examples

- **02_reproducibility**: Learn about data tracking and lineage
- **03_yaml_config**: Advanced configuration management
- **04_python_config**: Using Python for config definitions

## Additional Resources

- [FlexLock Documentation](https://github.com/quentinf00/flexlock)
- [@flexcli Documentation](../docs/flexcli.md)
- [Parallel Execution Guide](../docs/parallel.md)
