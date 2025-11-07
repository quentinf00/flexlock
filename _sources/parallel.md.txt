# Parallel Execution in FlexLock

FlexLock provides robust support for parallel execution of tasks, enabling you to scale your experiments efficiently. The parallel execution system is built around a centralized task queue mechanism and supports multiple execution backends.

## Overview

The parallel execution system works by:
1. Converting your tasks into a centralized task queue stored in a SQLite database
2. Distributing tasks dynamically to worker processes across different backends
3. Supporting both local execution and cluster schedulers (SLURM, PBS)
4. Providing fault tolerance through task persistence

## Running Tasks in Parallel Locally

When running tasks in parallel locally, FlexLock uses a pull-based model where multiple worker processes pull tasks from a shared SQLite database:

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

#### How Local Parallel Execution Works

1. **Task Queuing**: All tasks are first queued in a SQLite database (`run.lock.tasks.db`)
2. **Worker Spawning**: Multiple worker processes are spawned based on the `n_jobs` parameter
3. **Dynamic Task Distribution**: Workers continuously pull tasks from the database queue
4. **Result Aggregation**: Completed tasks are tracked in the database
5. **Fault Tolerance**: If a worker fails, its tasks remain in the queue for other workers

### Local Execution Parameters

- `n_jobs`: Number of local worker processes to spawn
- `local_workers`: Alternative way to specify the number of local workers
- Task distribution uses a pull model, so workers will continue working until the queue is empty

## Running Tasks with Cluster Schedulers

FlexLock supports execution on cluster schedulers like SLURM and PBS through dedicated backends.

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

## PBS Configuration Example

Here's a comprehensive example of a PBS configuration file:

```yaml
# pbs_config.yaml
# PBS resource allocation parameters
num_cpus: 4                    # Number of CPUs per node
time: "02:00:00"              # Walltime limit (HH:MM:SS)
queue: "sequentiel"                # Queue name to submit to

# Optional parameters
array_parallelism: 10         # Number of concurrent array jobs
extra_directives:
  - "#PBS -l mem=8gb"         # Additional memory requirement
  - "#PBS -m abe"             # Email notifications on abort, begin, end
  - 'eval "$(pixi shell-hook)"' # Activate environment

```

### PBS Configuration Options

- `num_cpus`: Number of CPUs to allocate per job
- `time`: Walltime limit for the job in HH:MM:SS format
- `queue`: Name of the PBS queue to submit to
- `array_parallelism`: For array jobs, specifies number of concurrent tasks
- `extra_directives`: List of additional PBS directives to include
- Additional custom parameters are passed through to the PBS script

### How PBS Backend Works

1. **Task Serialization**: Each task is serialized using cloudpickle
2. **PBS Script Generation**: FlexLock generates a PBS submission script with appropriate directives
3. **Job Submission**: The script is submitted to PBS using `qsub`
4. **Array Job Support**: For multiple tasks, FlexLock can submit a single PBS array job
5. **Task Distribution**: Each array job reads the task parameters using `PBS_ARRAY_INDEX`

## SLURM Configuration Example

```yaml
# slurm_config.yaml
cpus_per_task: 4              # Number of CPUs per task
time: "02:00:00"             # Walltime limit (HH:MM:SS)
partition: "batch"           # SLURM partition to use

# Optional parameters
array_parallelism: 10        # Number of concurrent array jobs
array_limit: 5               # Maximum number of concurrent array jobs running
extra_directives:
  - "#SBATCH --mail-type=ALL"# Email notifications
  - "#SBATCH --mail-user=user@domain.com" # Email address
  - 'eval "$(pixi shell-hook)"' # Activate environment

```

### How SLURM Backend Works

1. **Task Serialization**: Each task is serialized using cloudpickle
2. **SLURM Script Generation**: FlexLock generates a SLURM submission script with SBATCH directives
3. **Job Submission**: Script is submitted to SLURM using `sbatch`
4. **Module Loading**: Automatically loads Python module if available
5. **Array Job Support**: Uses `SLURM_ARRAY_TASK_ID` to determine which task to execute

## Task Distribution and Configuration Merging

The `task_to` parameter specifies how each task parameter should be merged into the configuration:

If task_to="param" and tasks=[1, 2, 3]
Then for the first task, cfg.param will be set to 1
For the second task, cfg.param will be set to 2, etc.

This allows for dynamic configuration updates for each task while maintaining the base configuration.


## Tips:
The state of the queue can be inspected using sqlite with commands like:

```bash
sqlite3 <path/to/save_dir>/run.lock.tasks.db 'SELECT status, count(*) as count, MIN(ts_start) as first_start, MAX(ts_end) as last_end  FROM tasks group by status;' -header -line
```

## Troubleshooting
The PBS script is stored in `save_dir/pbs_logs`
If you encounter issue you can try submitting it directly with qsub or even running the small dynamically generated python scirpt in it manually.

