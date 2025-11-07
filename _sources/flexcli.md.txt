# `flexcli`: Command-Line Interface

The `@flexcli` decorator is a powerful tool that bridges the gap between your Python configuration classes and a command-line interface. It allows you to define your parameters in a structured class and then override them from the command line, from configuration files, or when calling the function programmatically.

## Basic Usage

To use `@flexcli`, you need a configuration class with a **required `save_dir` field** and a main function decorated with it.

> **Important**: Your configuration class must include a `save_dir` field, as it's required by FlexLock for organizing logs, snapshots, and results.

```python
# process.py
from flexlock import flexcli

class Config:
    param = 1
    input_path = 'data/input.csv'
    save_dir = 'results/${vinc:process}'  # Required field (see dave_dir configuration below for more info about the ${vinc:}

@flexcli(default_config=Config)
def main(cfg: Config): # type hint useful for tab completion
    print(f"Parameter: {cfg.param}")
    print(f"Input path: {cfg.input_path}")
    print(f"Save directory: {cfg.save_dir}")

if __name__ == '__main__':
    main()
```

This script can now be run in several ways:

### 1. Default Configuration

Run the script without any arguments to use the default values defined in the `Config` class.

```bash
python process.py
# Parameter: 1
# Input path: data/input.csv
# Save directory: results/process
```

### 2. Overriding Parameters from the CLI

You can override any parameter using the `-o` or `--override` flag.

```bash
python process.py -o param=10
# Parameter: 10
# Input path: data/input.csv
# Save directory: results/process
```

### 3. Using a Configuration File

For more complex configurations, you can use a YAML file.

```yaml
# conf/production.yml
param: 100
save_dir: /data/prod/process
```

Then, run the script with the `--config` flag:

```bash
python process.py --config conf/production.yml
# Parameter: 100
# Input path: data/input.csv
# Save directory: /data/prod/process
```

### 4. Using Multi-Stage Configuration Files

You can store multiple configurations in a single YAML file.

```yaml
# conf/experiments.yml
base_config:
  input_path: data/input.csv

experiment_a:
  param: 5
  input_path: ${base_config.input_path} # Supports omegaconf interpolation
  save_dir: results/exp_a

experiment_b:
  param: 10
  input_path: ${base_config.input_path}
  save_dir: results/exp_b
```

Use the `--experiment` flag to select a specific configuration:

```bash
python process.py --config conf/experiments.yml --experiment experiment_b
# Parameter: 10
# Input path: data/input.csv
# Save directory: results/exp_b
```

## Parallelization

`@flexcli` also provides built-in support for running multiple tasks in parallel.

### 1. Local Parallelization

If you have a list of parameters you want to run, you can use the `--tasks` and `--task_to` flags.

```bash
# tasks.txt
1
2
3
4
5
```

The following command will run the `main` function 5 times, with `param` being set to 1, 2, 3, 4, and 5 respectively. It will run up to 10 jobs in parallel on your local machine.

```bash
python process.py --tasks tasks.txt --task_to param --n_jobs=10
```

### 2. Slurm Parallelization

If you are working on a cluster with Slurm, you can distribute your jobs across the cluster.

```bash
python process.py --tasks tasks.txt --task_to param --slurm_config=slurm.yaml
```

The `slurm.yaml` file contains the configuration for the Slurm job (e.g., partition, memory, time).

### 3. PBS Parallelization

If you are working on a cluster with PBS, you can distribute your jobs across the cluster.

```bash
python process.py --tasks tasks.txt --task_to param --pbs_config=pbs.yaml
```

The `pbs.yaml` file contains the configuration for the PBS job (e.g., queue, nodes, walltime).


## Save dir configuration

The `save_dir` field is essential to FlexLock's functionality and serves as the primary location for organizing experiment artifacts. When a `save_dir` is specified, FlexLock automatically creates several important files and directories:

### Files and Directories Created in save_dir

1. **`config.yaml`**: A saved copy of the resolved configuration that was used for the run. This provides full provenance of the parameters used.

2. **`run.lock`**: The run lock file created by the `snapshot` function, containing:
   - Complete configuration state
   - Git commit hashes for reproducibility
   - Data hashes to track input dependencies
   - Information about previous experiment stages
   - Caller information (module, function, file path)

3. **`run.lock.tasks.db`**: A SQLite database used for task management during parallel execution. This enables:
   - Dynamic task distribution across multiple workers
   - Fault tolerance (failed tasks can be resumed)
   - Task status tracking (pending, completed, failed)

4. **Backend-specific log directories**:
   - `slurm_logs/` when using SLURM backend
   - `pbs_logs/` when using PBS backend
   These contain the submission scripts and output logs from the cluster scheduler.

### Using Resolvers for Dynamic save_dir Generation

FlexLock provides special resolvers that can be used within configuration files to generate dynamic values. Two particularly useful resolvers for `save_dir` and other path fields are `vinc` (version increment) and `now`.

#### `now` Resolver

The `now` resolver returns the current timestamp as a formatted string. This is useful for creating time-stamped directories.

```yaml
# config.yml
param: 5
save_dir: results/run_${now:%Y-%m-%d_%H-%M-%S}  # Creates timestamped directory
```

When loaded, this configuration will create a save directory like `results/run_2025-11-07_10-30-45`.

#### `vinc` Resolver

The `vinc` resolver finds the highest existing version of a folder/file and returns the next versioned path. This is useful for creating sequentially numbered experiment directories.

```yaml
# config.yml
param: 5
save_dir: results/exp_${vinc:}  # Creates exp_0001, exp_0002, etc.
```

If you already have `results/exp_0001` and `results/exp_0002`, this will create `results/exp_0003`.

