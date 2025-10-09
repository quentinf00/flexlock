# `flexcli`: Command-Line Interface

The `@flexcli` decorator is a powerful tool that bridges the gap between your Python configuration classes and a command-line interface. It allows you to define your parameters in a structured class and then override them from the command line, from configuration files, or when calling the function programmatically.

## Basic Usage

To use `@flexcli`, you need a configuration class and a main function decorated with it.

```python
# process.py
from flexlock import flexcli

class Config:
    param = 1
    input_path = 'data/input.csv'
    save_dir = 'results/process'

@flexcli(config_class=Config)
def main(cfg: Config):
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
defaults:
  - base_config

base_config:
  input_path: data/input.csv

experiment_a:
  param: 5
  save_dir: results/exp_a

experiment_b:
  param: 10
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
