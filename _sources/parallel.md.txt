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
- `containerization`: (Optional) Set to `singularity` or `docker` to run the job in a container.
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

This example submits a job to the `sequentiel` queue with a 2-hour walltime.

```yaml
# pbs_config.yaml
startup_lines:
  - "#PBS -N flexlock-experiment"
  - "#PBS -l nodes=1:ncpus=4"
  - "#PBS -l walltime=02:00:00"
  - "#PBS -l mem=8gb"
  - "#PBS -q sequentiel"
  - "#PBS -m abe" # Email notifications
  # Activate pixi environment
  - 'eval "$(pixi shell-hook)"'
```

## Containerized Execution

FlexLock supports running jobs in Singularity or Docker containers for maximum reproducibility.

### Container Configuration Example (Singularity)

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

### Building the Container

You can use the `singularity.def` and `Dockerfile` provided in the project to build a container image with your `pixi` environment pre-installed.

**Singularity:**
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

## Troubleshooting
The submission scripts and logs are stored in `save_dir/slurm_logs` or `save_dir/pbs_logs`. If you encounter issues, you can inspect the generated script and try submitting it directly or even running the Python code within it manually.

