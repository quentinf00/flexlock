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

## Troubleshooting
The submission scripts and logs are stored in `save_dir/slurm_logs` or `save_dir/pbs_logs`. If you encounter issues, you can inspect the generated script and try submitting it directly or even running the Python code within it manually.

