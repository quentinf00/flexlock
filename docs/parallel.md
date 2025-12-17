# Parallel Execution in FlexLock

FlexLock provides robust support for parallel execution of tasks, enabling you to scale your experiments efficiently. The parallel execution system is built around a centralized task queue mechanism and supports multiple execution backends.

## Overview

The parallel execution system works by:
1. Converting your tasks into a centralized task queue stored in a SQLite database
2. Distributing tasks dynamically to worker processes across different backends
3. Supporting both local execution and cluster schedulers (SLURM, PBS)
4. Providing fault tolerance through task persistence

## Running Tasks in Parallel Locally

Local parallel execution is ideal for development and smaller-scale experiments on a single machine. FlexLock uses a pull-based model where multiple worker processes pull tasks from a shared SQLite database.

### Basic Local Parallel Execution

```python
from flexlock import flexcli

class Config:
    param: int = 1
    save_dir: str = "results/experiment"

@flexcli(config_class=Config)
def main(cfg: Config):
    # Your function that will be executed in parallel
    def process_task(task_param):
        # Do work with task_param
        result = task_param * 2  # Example processing
        return result
    
    # Define your tasks
    tasks = [1, 2, 3, 4, 5]  # List of parameters to process
    
    # Execute tasks in parallel locally
    from flexlock.parallel import ParallelExecutor
    
    executor = ParallelExecutor(
        func=process_task,
        tasks=tasks,
        task_to="param",  # Which config field to update with each task
        cfg=cfg,
        n_jobs=4  # Number of parallel processes
    )
    executor.run()
```

### Using the CLI for Local Parallel Execution

You can also use the CLI to run multiple tasks in parallel:

```bash
# Define tasks in a text file
echo -e "1\n2\n3\n4\n5" > tasks.txt

# Run with 4 parallel processes
python script.py --tasks tasks.txt --task_to param --n_jobs=4
```

## Running Tasks with Cluster Schedulers

For large--scale experiments, FlexLock supports execution on cluster schedulers like SLURM and PBS. The configuration is managed through a single YAML file, giving you full control over the job submission script.

### SLURM Backend

To use the SLURM backend, specify a SLURM configuration file:

```bash
python script.py --tasks tasks.txt --task_to param --slurm_config slurm_config.yaml
```

### PBS Backend

To use the PBS backend, specify a PBS configuration file:

```bash
python script.py --tasks tasks.txt --task_to param --pbs_config pbs_config.yaml
```

## HPC Backend Configuration

The configuration for both SLURM and PBS backends follows the same structure, allowing you to define scheduler directives, logging, and containerization options.

- `startup_lines`: A list of strings that will be placed at the top of the submission script. This is where you define all your scheduler directives (e.g., `#SBATCH`, `#PBS`), environment setup, and module loads.
- `configure_logging`: (Optional, default: `True`) If true, FlexLock will automatically add directives to write the job's stdout and stderr to files in the backend's log directory (e.g., `save_dir/slurm_logs/`).
- `python_exe`: (Optional, default: `"python"`) The python executable to use. This is particularly useful for containerized execution, where it can be set to a `singularity run` command.
- `containerization`: (Optional) Set to `singularity` or `docker` to run the job in a container. Note: For the PBS backend, containerization is configured via the `python_exe` parameter.
- `container_image`: (Required if `containerization` is set) The path to the container image file (e.g., a `.sif` file for Singularity).
- `bind_mounts`: (Optional) A list of paths to bind mount into the container, in the format `host_path:container_path`. The directory containing the task data is always mounted automatically.

### SLURM Configuration Example

This example submits a 10-task job array, with each task requesting 4 CPUs and 8GB of memory.

```yaml
# slurm_config.yaml
startup_lines:
  - "#SBATCH --partition=batch"
  - "#SBATCH --job-name=flexlock-experiment"
  - "#SBATCH --nodes=1"
  - "#SBATCH --ntasks=1"
  - "#SBATCH --cpus-per-task=4"
  - "#SBATCH --mem=8gb"
  - "#SBATCH --time=02:00:00"
  # Submit as a 10-task job array
  - "#SBATCH --array=0-9"
  # Activate pixi environment
  - 'eval "$(pixi shell-hook)"'

# FlexLock will add #SBATCH --output and --error directives
configure_logging: true
```

### PBS Configuration Example

This example submits a 2-task job array to the `sequentiel` queue with a 5-minute walltime. Note that by default, FlexLock will add the `#PBS -N`, `#PBS -o` and `#PBS -e` directives.

```yaml
# pbs_config.yaml
startup_lines:
  - "#PBS -l select=mem=4gb:ncpus=1"
  - '#PBS -l walltime=00:05:00'
  - '#PBS -q sequentiel'
  # Submit as a 2-task job array
  - '#PBS -J 0-1'
  # Merge stdout and stderr
  - '#PBS -k oe'
  # Make environment variables available to the job
  - '#PBS -V'
  # Change to the submission directory
  - 'cd $PBS_O_WORKDIR'
  # Activate pixi environment
  - 'eval "$(pixi shell-hook)"'
```

## Containerized Execution

FlexLock supports running jobs in Singularity or Docker containers for maximum reproducibility.

### Container Configuration Example (Singularity with SLURM)

This configuration will execute the job inside a Singularity container, bind-mounting a dataset directory.

```yaml
# slurm_config_singularity.yaml
startup_lines:
  - "#SBATCH --partition=batch"
  - "#SBATCH --cpus-per-task=2"
  - "#SBATCH --mem=4gb"
  - "#SBATCH --array=0-9"

# Container settings
containerization: singularity
container_image: /path/to/your/flexlock_env.sif
bind_mounts:
  - /path/to/host/data:/data
```

### Container Configuration Example (Singularity with PBS)

For the PBS backend, containerization is achieved by setting the `python_exe` to the `singularity` command.

```yaml
# pbs_config_singularity.yaml
startup_lines:
  - "#PBS -l select=mem=4gb:ncpus=1"
  - '#PBS -l walltime=00:05:00'
  - '#PBS -q sequentiel'
  - '#PBS -J 0-1'
  - '#PBS -k oe'
  - 'cd $PBS_O_WORKDIR'

python_exe: >-
  singularity run
  --bind $(pwd)/my_project:/app/my_project
  --bind $(pwd):/workspace 
  --pwd /workspace
  env.sif python

```

### Building the Container

You can use the `singularity.def` and `Dockerfile` provided in the project to build a container image with your `pixi` environment pre-installed.

**Singularity:**

A `singularity.def` file defines the recipe for building your container. Here is an example that starts from an Ubuntu base, installs pixi, and sets up the project environment.

```singularity
Bootstrap: docker
From: ubuntu:24.04

%files
    # Copy the project files required to build the environment into /app
    pyproject.toml /app/
    pixi.lock /app/
    README.md /app/

%post
    # Navigate to the app directory
    cd /app
    mkdir /app/my_awesome_project
    
    # Install the pixi environment based on the lock file.
    # This creates the environment inside the container at /app/.pixi
    apt-get update && apt-get install -y curl
    export PIXI_HOME=/pixi
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH=$PIXI_HOME/bin:$PATH
    pixi global install git
    echo which git
    pixi install --locked
    rm -rf $HOME/.cache

%environment
    # Set the default working directory for when the container runs
    export SINGULARITY_WORKDIR=/app
    export PIXI_HOME=/pixi
    export PATH=$HOME/.pixi/bin:$PATH
    eval "$(pixi  shell-hook --manifest-path /app --as-is)"


%runscript
    # Default command to run. The environment is already active.
    # This script will execute any commands passed to "singularity run".
    exec "$@"
```

You can then build the container image (`.sif` file) using:
```bash
# (May require sudo depending on system config)
singularity build flexlock.sif singularity.def
```

**Docker:**
```bash
docker build -t flexlock-env .
```

## How the HPC Backends Work

1. **Task Serialization**: The worker function and its arguments are serialized using `cloudpickle`.
2. **Script Generation**: FlexLock generates a submission script. It combines your `startup_lines` with a Python snippet that deserializes and executes the task.
3. **Job Submission**: The script is submitted to the scheduler using `sbatch` (Slurm) or `qsub` (PBS).
4. **Task Execution**: Inside the job, the Python snippet is executed. If it's a job array, the environment variable (`SLURM_ARRAY_TASK_ID` or `PBS_ARRAY_INDEX`) is used to identify which worker it is, though the workers themselves pull tasks dynamically from the central queue.

## Task Distribution and Configuration Merging

The `task_to` parameter specifies how each task parameter should be merged into the configuration:

If `task_to="param"` and `tasks=[1, 2, 3]`:
- For the first task, `cfg.param` will be set to 1.
- For the second task, `cfg.param` will be set to 2, and so on.

This allows for dynamic configuration updates for each task while maintaining the base configuration.

## Tips
The state of the queue can be inspected using sqlite with commands like:

```bash
sqlite3 <path/to/save_dir>/run.lock.tasks.db 'SELECT status, count(*) as count, MIN(ts_start) as first_start, MAX(ts_end) as last_end  FROM tasks group by status;' -header -line
```

---

## Task Database Deep Dive

FlexLock uses SQLite databases to manage distributed task execution. Understanding the database schema and available operations helps with monitoring, debugging, and advanced workflows.

### Database Location

Task databases are automatically created at:

```
<save_dir>/run.lock.tasks.db
```

**Example:** If your config has `save_dir: results/hp_sweep`, the database will be at:
```
results/hp_sweep/run.lock.tasks.db
```

### Database Schema

The task database has a single `tasks` table:

```sql
CREATE TABLE tasks (
    task_hash TEXT PRIMARY KEY,      -- Unique hash of task configuration
    status TEXT NOT NULL,             -- pending, running, done, failed
    task_data BLOB,                   -- Pickled task parameters
    snapshot_data TEXT,               -- JSON snapshot of task config (delta)
    ts_start REAL,                    -- Unix timestamp when task started
    ts_end REAL,                      -- Unix timestamp when task finished
    worker_id TEXT,                   -- Identifier of worker that processed task
    error TEXT                        -- Error message if status='failed'
);
```

**Field descriptions:**

- **task_hash**: SHA-256 hash of the task configuration, used as unique identifier
- **status**: One of `pending`, `running`, `done`, `failed`
- **task_data**: Serialized task parameters (Python pickle format)
- **snapshot_data**: JSON string containing the task's delta snapshot
- **ts_start**: When the task was claimed by a worker (Unix timestamp)
- **ts_end**: When the task completed or failed (Unix timestamp)
- **worker_id**: Identifier of the worker (e.g., hostname, SLURM job ID)
- **error**: Error message and traceback if task failed

### Querying Task Status

#### Status Summary

Get an overview of task statuses:

```bash
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT status, COUNT(*) as count FROM tasks GROUP BY status;"
```

**Example output:**
```
pending|5
running|3
done|42
failed|2
```

#### Detailed Status with Timing

```bash
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT status,
          COUNT(*) as count,
          MIN(ts_start) as first_start,
          MAX(ts_end) as last_end
   FROM tasks
   GROUP BY status;" \
  -header -line
```

**Example output:**
```
status = pending
  count = 5
  first_start =
  last_end =

status = done
  count = 42
  first_start = 1734355200.5
  last_end = 1734358800.3
```

#### Find Failed Tasks

```bash
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT task_hash, worker_id, error
   FROM tasks
   WHERE status='failed';"
```

#### Check Task Timing

Find longest-running tasks:

```bash
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT task_hash,
          (ts_end - ts_start) as duration_seconds,
          status
   FROM tasks
   WHERE status='done'
   ORDER BY duration_seconds DESC
   LIMIT 10;" \
  -header -column
```

#### Monitor Running Tasks

```bash
# Watch running tasks in real-time
watch -n 5 "sqlite3 results/sweep/run.lock.tasks.db \
  \"SELECT COUNT(*) as running FROM tasks WHERE status='running'\""
```

### Programmatic Access

Use FlexLock's taskdb module for programmatic access:

```python
from flexlock.taskdb import (
    get_task_snapshot,
    list_task_snapshots,
    pending_count
)

# Get snapshot for specific task
db_path = "results/sweep/run.lock.tasks.db"
task_hash = "abc123def456"
snapshot = get_task_snapshot(db_path, task_hash)
print(snapshot)  # Dict with task configuration and data

# List all tasks
all_tasks = list_task_snapshots(db_path)
for task_hash, snapshot, status in all_tasks:
    print(f"{task_hash[:8]}: {status}")

# List only completed tasks
done_tasks = list_task_snapshots(db_path, status="done")
print(f"Completed tasks: {len(done_tasks)}")

# Check pending count
n_pending = pending_count(db_path)
print(f"Tasks remaining: {n_pending}")
```

### Resuming Failed Runs

The task database enables automatic fault tolerance. If a sweep is interrupted:

1. **Check current status:**
   ```bash
   sqlite3 results/sweep/run.lock.tasks.db \
     "SELECT status, COUNT(*) FROM tasks GROUP BY status;"
   ```

   **Output:**
   ```
   pending|15
   running|0
   done|35
   failed|5
   ```

2. **Rerun the same command:**
   ```bash
   # Just rerun - completed tasks are automatically skipped
   python train.py --sweep-file sweep.yaml --n_jobs 4
   ```

3. **What happens:**
   - Tasks with `status='done'` are skipped
   - Tasks with `status='pending'` or `status='failed'` are executed
   - New worker IDs are assigned to retried tasks

### Manual Task Management

**Warning:** Only modify the database when no workers are running to avoid corruption.

#### Reset Failed Tasks to Pending

```bash
sqlite3 results/sweep/run.lock.tasks.db \
  "UPDATE tasks SET status='pending' WHERE status='failed';"
```

#### Clear Specific Task

```bash
# Find task hash first
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT task_hash FROM tasks WHERE status='failed' LIMIT 1;"

# Delete it
sqlite3 results/sweep/run.lock.tasks.db \
  "DELETE FROM tasks WHERE task_hash='abc123...';"
```

#### Mark Running Tasks as Pending (After Crash)

If workers crashed and left tasks in `running` state:

```bash
sqlite3 results/sweep/run.lock.tasks.db \
  "UPDATE tasks SET status='pending' WHERE status='running';"
```

### Debugging Task Failures

#### View Error Messages

```bash
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT task_hash, error
   FROM tasks
   WHERE status='failed';" \
  -header -column
```

#### Inspect Failed Task Configuration

```python
import sqlite3
import pickle
import json

db_path = "results/sweep/run.lock.tasks.db"
conn = sqlite3.connect(db_path)

# Get failed task
cursor = conn.execute(
    "SELECT task_hash, task_data, snapshot_data, error "
    "FROM tasks WHERE status='failed' LIMIT 1"
)
task_hash, task_blob, snapshot_json, error = cursor.fetchone()

print(f"Task hash: {task_hash}")
print(f"Error: {error}")

# Unpickle task data
task_data = pickle.loads(task_blob)
print(f"Task config: {task_data}")

# Parse snapshot
snapshot = json.loads(snapshot_json) if snapshot_json else None
print(f"Snapshot: {snapshot}")

conn.close()
```

#### Reproduce Failure Locally

```python
from flexlock.taskdb import get_task_snapshot

# Get failed task configuration
snapshot = get_task_snapshot("results/sweep/run.lock.tasks.db", "abc123...")

# Reproduce locally
from your_module import main
try:
    main(snapshot['config'])
except Exception as e:
    print(f"Reproduced error: {e}")
    import traceback
    traceback.print_exc()
```

### Export Tasks for Analysis

Use `flexlock-export` to extract task snapshots:

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

See [CLI Tools documentation](./cli_tools.md#flexlock-export-extract-snapshots) for more on `flexlock-export`.

### Task Snapshot Storage

Starting from FlexLock v0.3+, task snapshots are stored **in the database** rather than separate files:

**Old behavior (< v0.3):**
```
results/sweep/
├── run.lock              # Master snapshot
├── run.lock.tasks.db     # Task queue only
└── task_abc123/
    └── run.lock          # Task snapshot files
```

**New behavior (>= v0.3):**
```
results/sweep/
├── run.lock              # Master snapshot
├── run.lock.tasks.db     # Task queue + snapshots
└── run.lock.tasks        # Exported YAML (optional)
```

**Benefits:**
- ✅ **Atomic updates**: Snapshot and status updated together
- ✅ **Faster**: No file I/O per task
- ✅ **Cleaner**: No proliferation of directories
- ✅ **Portable**: Single database file

**Accessing snapshots:**
```python
from flexlock.taskdb import get_task_snapshot

# Retrieve snapshot from database
snapshot = get_task_snapshot("results/sweep/run.lock.tasks.db", task_hash)
```

### Database Maintenance

#### Vacuum Database

Reclaim space after deleting many tasks:

```bash
sqlite3 results/sweep/run.lock.tasks.db "VACUUM;"
```

#### Backup Database

```bash
# Copy database file
cp results/sweep/run.lock.tasks.db backups/sweep_2025_12_16.db

# Or use SQLite backup command
sqlite3 results/sweep/run.lock.tasks.db ".backup backups/sweep.db"
```

#### Check Database Size

```bash
ls -lh results/sweep/run.lock.tasks.db
```

Large databases (>1GB) may benefit from periodic vacuuming or exporting completed tasks and archiving.

### Advanced Queries

#### Find Outliers (Unusually Long Tasks)

```bash
sqlite3 results/sweep/run.lock.tasks.db <<EOF
SELECT task_hash,
       (ts_end - ts_start) as duration,
       status
FROM tasks
WHERE status='done'
  AND duration > (
    SELECT AVG(ts_end - ts_start) * 3
    FROM tasks
    WHERE status='done'
  )
ORDER BY duration DESC;
EOF
```

#### Worker Performance

```bash
sqlite3 results/sweep/run.lock.tasks.db \
  "SELECT worker_id,
          COUNT(*) as tasks_completed,
          AVG(ts_end - ts_start) as avg_duration
   FROM tasks
   WHERE status='done'
   GROUP BY worker_id
   ORDER BY tasks_completed DESC;" \
  -header -column
```

#### Task Completion Rate Over Time

```bash
sqlite3 results/sweep/run.lock.tasks.db <<EOF
SELECT datetime(ts_end, 'unixepoch', 'localtime') as completion_time,
       COUNT(*) as tasks
FROM tasks
WHERE status='done'
GROUP BY datetime(ts_end, 'unixepoch', 'localtime', 'start of hour')
ORDER BY completion_time;
EOF
```

### Best Practices

1. **Don't modify database while workers are running**
   - Risk of database corruption
   - Use `flexlock-export` instead to extract results

2. **Back up before manual edits**
   ```bash
   cp tasks.db tasks.db.backup
   # Now safe to modify
   sqlite3 tasks.db "UPDATE ..."
   ```

3. **Use exported snapshots for analysis**
   ```bash
   # Extract snapshots first
   flexlock-export --db tasks.db --out analysis/
   # Analyze from files, not database
   python analyze.py analysis/
   ```

4. **Monitor database size**
   - Large sweeps can create large databases
   - Consider exporting and archiving old sweeps

5. **Use transactions for multiple updates**
   ```bash
   sqlite3 tasks.db <<EOF
   BEGIN TRANSACTION;
   UPDATE tasks SET status='pending' WHERE status='failed';
   DELETE FROM tasks WHERE status='cancelled';
   COMMIT;
   EOF
   ```

6. **Enable WAL mode for better concurrency** (done automatically by FlexLock)
   ```bash
   sqlite3 tasks.db "PRAGMA journal_mode=WAL;"
   ```

### Integration with CI/CD

Monitor sweep progress in CI/CD pipelines:

```bash
#!/bin/bash
# check_sweep_status.sh

DB="results/sweep/run.lock.tasks.db"

# Check if sweep is complete
PENDING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE status='pending';")
RUNNING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE status='running';")
FAILED=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE status='failed';")
DONE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE status='done';")

echo "Status: $DONE done, $RUNNING running, $PENDING pending, $FAILED failed"

if [ "$FAILED" -gt 0 ]; then
    echo "ERROR: $FAILED tasks failed"
    exit 1
elif [ "$PENDING" -eq 0 ] && [ "$RUNNING" -eq 0 ]; then
    echo "SUCCESS: All tasks completed"
    exit 0
else
    echo "IN PROGRESS: $((PENDING + RUNNING)) tasks remaining"
    exit 2
fi
```

### Summary

FlexLock's task database provides:

- ✅ **Centralized queue**: All workers coordinate via SQLite
- ✅ **Fault tolerance**: Resume interrupted sweeps automatically
- ✅ **Status tracking**: Monitor progress in real-time
- ✅ **Snapshot storage**: Delta snapshots stored in database
- ✅ **Queryable**: SQL access for monitoring and debugging
- ✅ **Portable**: Single file contains entire sweep state

**Key operations:**
- **Query status**: `sqlite3 tasks.db "SELECT status, COUNT(*) ..."`
- **List snapshots**: `list_task_snapshots(db_path)`
- **Export tasks**: `flexlock-export --db tasks.db --out results/`
- **Resume failed runs**: Just rerun the same command

Understanding the task database unlocks powerful workflows for managing large-scale experiments.

---

## Troubleshooting
The submission scripts and logs are stored in `save_dir/slurm_logs` or `save_dir/pbs_logs`. If you encounter issues, you can inspect the generated script and try submitting it directly or even running the Python code within it manually.

