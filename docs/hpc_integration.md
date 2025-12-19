# HPC Integration

FlexLock provides seamless integration with HPC cluster schedulers (PBS and Slurm) for running experiments at scale.

## Overview

FlexLock's HPC integration allows you to:

- ✅ Submit jobs to PBS or Slurm queues with a single parameter
- ✅ Monitor job status in real-time with `flexlock-status`
- ✅ Wait for job completion or submit and continue
- ✅ Run parameter sweeps across cluster nodes
- ✅ Use Singularity containers for reproducible environments
- ✅ Automatic task database for distributed job management

## Quick Start

### Basic HPC Submission

```python
from flexlock.api import Project

proj = Project(defaults='configs.defaults')
config = proj.get('train')

# Submit to PBS and wait for completion
result = proj.submit(
    config,
    pbs_config='configs/pbs.yaml',
    wait=True
)

print(f"Accuracy: {result.accuracy}")
```

### Non-Blocking Submission

```python
# Submit and continue without waiting
result = proj.submit(
    config,
    pbs_config='configs/pbs.yaml',
    wait=False
)

print("Job submitted")
# Job continues running on cluster
```

### Monitor Job Status

```bash
# Real-time monitoring
flexlock-status outputs/train/run.lock.tasks.db --watch

# Check failed tasks
flexlock-status outputs/train/run.lock.tasks.db --failed --verbose
```

## PBS Configuration

### Basic PBS Config

Create `configs/pbs.yaml`:

```yaml
startup_lines:
  - "#PBS -l select=mem=4gb:ncpus=1"
  - '#PBS -N my_job'
  - '#PBS -l walltime=00:30:00'
  - '#PBS -q default'
  - '#PBS -V'  # Export environment
  - 'cd $PBS_O_WORKDIR'
  - 'eval "$(pixi shell-hook)"'  # Activate environment

python_exe: python
```

### GPU Jobs

```yaml
startup_lines:
  - "#PBS -l select=mem=32gb:ncpus=8:ngpus=1"
  - '#PBS -N gpu_training'
  - '#PBS -l walltime=12:00:00'
  - '#PBS -q gpu'
  - '#PBS -V'
  - 'cd $PBS_O_WORKDIR'
  - 'module load cuda/11.8'
  - 'eval "$(pixi shell-hook)"'

python_exe: python
```

### High-Memory Jobs

```yaml
startup_lines:
  - "#PBS -l select=mem=128gb:ncpus=32"
  - '#PBS -N big_memory'
  - '#PBS -l walltime=48:00:00'
  - '#PBS -q highmem'
  - '#PBS -V'
  - 'cd $PBS_O_WORKDIR'
  - 'eval "$(pixi shell-hook)"'

python_exe: python
```

## Slurm Configuration

### Basic Slurm Config

Create `configs/slurm.yaml`:

```yaml
startup_lines:
  - "#SBATCH --mem=4G"
  - "#SBATCH --cpus-per-task=1"
  - "#SBATCH --time=00:30:00"
  - "#SBATCH --partition=default"
  - "#SBATCH --job-name=my_job"
  - 'cd $SLURM_SUBMIT_DIR'
  - 'source activate myenv'

python_exe: python
```

### GPU with Slurm

```yaml
startup_lines:
  - "#SBATCH --mem=32G"
  - "#SBATCH --cpus-per-task=8"
  - "#SBATCH --gres=gpu:1"
  - "#SBATCH --time=12:00:00"
  - "#SBATCH --partition=gpu"
  - 'cd $SLURM_SUBMIT_DIR'
  - 'module load cuda/11.8'
  - 'source activate myenv'

python_exe: python
```

## Singularity Containers

Singularity integration happens through the `python_exe` parameter:

### PBS + Singularity

```yaml
# configs/pbs_singularity.yaml
startup_lines:
  - "#PBS -l select=mem=4gb:ncpus=1"
  - '#PBS -N container_job'
  - '#PBS -l walltime=00:30:00'
  - '#PBS -q default'
  - '#PBS -V'
  - 'cd $PBS_O_WORKDIR'
  - 'module load singularity'  # If needed

python_exe: >-
  singularity run
  --bind $(pwd):/workspace
  --pwd /workspace
  my_env.sif python
```

**Key points:**
- `--bind`: Mount host directories into container
- `--pwd`: Set working directory inside container
- `my_env.sif`: Your container image
- `python`: Command to run inside container

### Slurm + Singularity

```yaml
# configs/slurm_singularity.yaml
startup_lines:
  - "#SBATCH --mem=4G"
  - "#SBATCH --cpus-per-task=1"
  - 'cd $SLURM_SUBMIT_DIR'

python_exe: >-
  singularity run
  --bind $(pwd):/workspace
  --pwd /workspace
  env.sif python
```

### GPU Containers

```yaml
python_exe: >-
  singularity run --nv
  --bind $(pwd):/workspace
  --bind /data:/data
  gpu-env.sif python
```

**Note:** `--nv` enables NVIDIA GPU access.

## Parameter Sweeps on HPC

Run multiple experiments in parallel across cluster nodes:

### Basic Sweep

```python
from flexlock.api import Project

proj = Project(defaults='configs.defaults')
config = proj.get('train')

# Define parameter grid
sweep_grid = [
    {"lr": 0.001, "epochs": 10},
    {"lr": 0.01, "epochs": 10},
    {"lr": 0.05, "epochs": 10},
    {"lr": 0.1, "epochs": 10},
]

# Submit sweep to HPC
results = proj.submit(
    config,
    sweep=sweep_grid,
    pbs_config='configs/pbs.yaml',
    wait=True,
    n_jobs=4  # Submit 4 parallel jobs
)

# Find best configuration
best_idx = max(range(len(results)),
               key=lambda i: results[i].get('accuracy', 0))
best = results[best_idx]
print(f"Best: lr={best.lr}, accuracy={best.accuracy}")
```

### Large Sweeps

For large sweeps, use job arrays:

```yaml
# configs/pbs_array.yaml
startup_lines:
  - "#PBS -J 0-99"  # Job array with 100 tasks
  - "#PBS -l select=mem=4gb:ncpus=1"
  - '#PBS -l walltime=01:00:00'
  - '#PBS -V'
  - 'cd $PBS_O_WORKDIR'

python_exe: python
```

Each array task pulls work from the shared task database.

## Wait Behavior

The `wait` parameter controls whether `submit()` blocks:

### wait=True (Blocking)

```python
# Blocks until job completes
result = proj.submit(
    config,
    pbs_config='pbs.yaml',
    wait=True  # Blocks here
)

# Results immediately available
print(result.accuracy)
```

**How it works:**
1. Submit job to cluster
2. Poll task database every 1 second (configurable)
3. Log progress every 10 seconds
4. Return when all tasks complete

**Use cases:**
- Sequential pipelines
- Immediate result analysis
- CI/CD workflows

### wait=False (Non-Blocking)

```python
# Returns immediately
result = proj.submit(
    config,
    pbs_config='pbs.yaml',
    wait=False  # Returns immediately
)

print("Job submitted, continuing...")
# result.status == "SUBMITTED"
# Job continues on cluster
```

**Use cases:**
- Submit many jobs at once
- Long-running experiments
- Interactive workflows

**Monitor later:**
```bash
flexlock-status outputs/train/run.lock.tasks.db --watch
```

## Monitoring Jobs

### Real-Time Status

```bash
# Watch job progress
flexlock-status outputs/sweep/run.lock.tasks.db --watch
```

Output:
```
============================================================
Task Status Summary
============================================================
Pending:       12
Running:        3
Done:          45
Failed:         2
------------------------------------------------------------
Total:         62
Progress:    75.8% (47/62 completed)

Status:     ⏳ In progress
============================================================

Refreshing in 10s... (Ctrl+C to stop)
```

### Check Failed Tasks

```bash
flexlock-status outputs/sweep/run.lock.tasks.db --failed --verbose
```

Shows:
- Task configurations that failed
- Full error tracebacks
- Node where failure occurred
- Timestamps

### List All Tasks

```bash
# All tasks
flexlock-status outputs/sweep/run.lock.tasks.db --all

# Filter by status
flexlock-status outputs/sweep/run.lock.tasks.db --all --status running
flexlock-status outputs/sweep/run.lock.tasks.db --all --status failed
```

## Smart Caching with HPC

FlexLock's smart run detection works seamlessly with HPC:

```python
# First run - executes on cluster
result = proj.submit(
    config,
    pbs_config='pbs.yaml',
    smart_run=True,  # Check cache
    wait=True
)

# Second run - uses cached results!
result = proj.submit(
    config,
    pbs_config='pbs.yaml',
    smart_run=True,  # Cache hit!
    wait=True
)
# No job submitted, instant results
```

**Benefits:**
- Skip completed work
- Resume failed sweeps
- Incremental parameter exploration

## Multi-Stage Pipelines on HPC

Run complex pipelines on the cluster:

```python
from flexlock.api import Project

proj = Project(defaults='pipeline.defaults')

# Stage 1: Preprocess (on cluster)
preprocess = proj.submit(
    proj.get('preprocess'),
    pbs_config='pbs.yaml',
    smart_run=True,
    wait=True  # Wait for preprocessing
)

# Stage 2: Train (uses preprocessing output)
train = proj.submit(
    proj.get('train'),
    pbs_config='pbs_gpu.yaml',  # Different queue
    smart_run=True,
    wait=True
)

# Stage 3: Evaluate
evaluate = proj.submit(
    proj.get('evaluate'),
    pbs_config='pbs.yaml',
    smart_run=True,
    wait=True
)

print(f"Final accuracy: {evaluate.accuracy}")
```

## Advanced Usage

### Custom Timeout

```python
from flexlock.parallel import ParallelExecutor

executor = ParallelExecutor(
    func=my_function,
    tasks=task_list,
    cfg=config,
    pbs_config='pbs.yaml'
)

# Wait with 2-hour timeout
success = executor.run(
    wait=True,
    timeout=7200,      # 2 hours
    poll_interval=30   # Check every 30s
)

if not success:
    print("Jobs did not complete in time")
```

### Job Dependencies

```python
# Sequential execution
preprocess = proj.submit(cfg1, pbs_config='pbs.yaml', wait=True)
train = proj.submit(cfg2, pbs_config='pbs.yaml', wait=True)
```

### Multiple Queue Types

```python
# Fast queue for preprocessing
preprocess = proj.submit(
    preprocess_cfg,
    pbs_config='configs/pbs_fast.yaml'
)

# GPU queue for training
train = proj.submit(
    train_cfg,
    pbs_config='configs/pbs_gpu.yaml'
)

# Highmem queue for analysis
analyze = proj.submit(
    analyze_cfg,
    pbs_config='configs/pbs_highmem.yaml'
)
```

## Troubleshooting

### Job Fails Immediately

**Check PBS error logs:**
```bash
cat outputs/job/pbs_logs/pbs.err
```

**Common causes:**
- Environment not activated
- Python not found
- Wrong working directory

**Fix:** Ensure PBS config has proper setup:
```yaml
startup_lines:
  - 'cd $PBS_O_WORKDIR'  # Critical!
  - 'eval "$(pixi shell-hook)"'  # Or your env activation
```

### Job Stuck in Queue

**Check queue status:**
```bash
qstat -Q  # PBS
squeue    # Slurm
```

**Possible issues:**
- Insufficient resources
- Queue limits reached
- Wrong queue specified

### Task Database Locked

**Symptom:** "Database locked" errors.

**Cause:** Multiple workers accessing simultaneously (normal).

**Solution:** FlexLock handles this automatically with retries. If persistent:
```python
# Increase timeout in config
c.execute("PRAGMA busy_timeout=30000")  # 30 seconds
```

### Jobs Not Completing

**Check with flexlock-status:**
```bash
flexlock-status outputs/job/run.lock.tasks.db --all
```

**Look for:**
- Tasks stuck in "running" status
- Failed tasks with errors

### Results Not Loading

**Verify results file exists:**
```bash
ls outputs/job/results.json
```

**If missing:**
- Check if job actually completed
- Verify save_dir in config
- Check PBS output logs

## Best Practices

### ✅ Do:

1. **Test locally first**: Run with `smart_run=True` locally before HPC
2. **Use wait=True for pipelines**: Ensures stages complete in order
3. **Monitor actively**: Use `flexlock-status --watch` for first runs
4. **Set reasonable walltimes**: Don't request more than needed
5. **Use containers**: For reproducibility across systems
6. **Smart caching**: Use `smart_run=True` to skip completed work

### ❌ Don't:

1. **Submit to login nodes**: Always use the scheduler
2. **Hardcode paths**: Use `$PBS_O_WORKDIR` or relative paths
3. **Ignore resource limits**: Stay within your allocation
4. **Submit thousands of tiny jobs**: Use job arrays or batch tasks
5. **Skip environment activation**: Jobs will fail mysteriously

## Performance Tips

### 1. Batch Small Tasks

```python
# Bad: 1000 tiny jobs
proj.submit(cfg, sweep=big_grid, n_jobs=1000)

# Good: 100 jobs, each processing ~10 tasks
proj.submit(cfg, sweep=big_grid, n_jobs=100)
```

### 2. Use Smart Caching

```python
# Skip completed work automatically
result = proj.submit(
    cfg,
    sweep=grid,
    smart_run=True,  # Critical!
    pbs_config='pbs.yaml'
)
```

### 3. Parallel Preprocessing

```python
# Preprocess once locally
preprocess = proj.submit(preprocess_cfg, smart_run=True)

# All HPC jobs use same preprocessed data
results = proj.submit(
    train_cfg,
    sweep=grid,
    pbs_config='pbs.yaml',
    smart_run=True
)
```

### 4. Choose Right Queue

```yaml
# Quick jobs - fast queue
walltime: 00:15:00
queue: fast

# Long jobs - normal queue
walltime: 48:00:00
queue: long

# GPU jobs - GPU queue
queue: gpu
```

## Example: Complete HPC Workflow

```python
#!/usr/bin/env python3
"""Complete HPC workflow example."""

from flexlock.api import Project
from loguru import logger

# Enable logging
logger.enable("flexlock")

def main():
    proj = Project(defaults='configs.defaults')

    # Define sweep
    sweep_grid = [
        {"lr": 0.001, "epochs": 10, "batch_size": 32},
        {"lr": 0.01, "epochs": 10, "batch_size": 32},
        {"lr": 0.05, "epochs": 10, "batch_size": 32},
        {"lr": 0.01, "epochs": 20, "batch_size": 64},
    ]

    logger.info(f"Submitting {len(sweep_grid)} jobs to HPC")

    # Submit to cluster
    results = proj.submit(
        proj.get('train'),
        sweep=sweep_grid,
        pbs_config='configs/pbs_gpu.yaml',
        smart_run=True,  # Skip completed
        wait=True,       # Block until done
        n_jobs=4         # Parallel jobs
    )

    # Analyze results
    logger.info("All jobs completed!")

    best_idx = max(range(len(results)),
                   key=lambda i: results[i].get('accuracy', 0))
    best = results[best_idx]

    logger.info(f"Best configuration:")
    logger.info(f"  lr={best.lr}")
    logger.info(f"  epochs={best.epochs}")
    logger.info(f"  batch_size={best.batch_size}")
    logger.info(f"  accuracy={best.accuracy:.2%}")

if __name__ == "__main__":
    main()
```

**Run it:**
```bash
# Submit and wait
python workflow.py

# Monitor in another terminal
flexlock-status outputs/train/run.lock.tasks.db --watch
```

## See Also

- **[Example 08: HPC Backend](../my_awesome_project/08_hpc_backend/)**: Detailed HPC examples
- **[Example 09: Containers](../my_awesome_project/09_container/)**: Singularity integration
- **[Example 10: Full Workflow](../my_awesome_project/10_full_workflow/)**: Complete feature showcase
- **[ParallelExecutor API](./api/parallel.md)**: Low-level backend control

## Summary

FlexLock makes HPC integration simple:

1. **Add one parameter**: `pbs_config='pbs.yaml'`
2. **Monitor easily**: `flexlock-status db_path --watch`
3. **Smart caching**: Automatic result reuse
4. **Container support**: Reproducible environments
5. **Flexible waiting**: Block or continue as needed

Start simple, scale to thousands of cluster jobs! 🚀
