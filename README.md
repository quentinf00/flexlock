# Naga

Naga is a lightweight Python library designed to bring clarity, reproducibility, and scalability to your computational experiments. It provides a set of explicit, composable tools to handle the boilerplate of experiment tracking, so you can focus on your core logic.

Naga is built on the philosophy that **explicit is better than implicit**. Instead of magical decorators, you use clear, standalone functions and context managers to manage the lifecycle of your run.

## Core Components

- **`naga.clicfg`**: A decorator to effortlessly create powerful command-line interfaces from your Python configuration classes.
- **`naga.runlock`**: A function to create a `run.lock` file—a definitive receipt of your experiment containing the config, data hashes, Git commits, and dependencies.
- **`naga.mlflow_lock`**: A context manager that handles the MLflow run lifecycle, including run creation, artifact logging, and logical run management.
- **`naga.unsafe_debug`**: A helper decorator for seamless debugging, dropping you into an interactive session with full context when an exception occurs.

## Installation

```bash
# With pixi
pixi add naga
```

## Quickstart

Let's start with a simple data processing script.

```python
# process.py
from pathlib import Path

class Config:
    param = 1
    input_path = 'data/preprocess/input.csv'
    save_dir = 'results/process'

def process(cfg: Config=Config()):
    print(f"Running with param: {cfg.param}")
    # Create dummy input if it doesn't exist
    Path(cfg.input_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.input_path).write_text("some data")

    # Core logic
    output_path = Path(cfg.save_dir) / 'out.txt'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        for _ in range(cfg.param):
            f.write(Path(cfg.input_path).read_text())
    print(f"Output written to {output_path}")

if __name__ == '__main__':
    process()
```

This is a standard Python script. Now, let's introduce Naga to add reproducibility and a powerful CLI.

### Step 1: Track Your Run with `runlock`

To ensure reproducibility, we need to track the configuration, code version, and data used in a run. `naga.runlock` creates a `run.lock` file with this information.

```python
# process.py
...
from naga import runlock

def process(cfg: Config=Config()):
    ...
    # Your core logic here...
    ...
    runlock(
        config=cfg,
        repos=['.'],  # Track the git version of the current repo
        data=[cfg.input_path],  # Hash the input data
        # prevs=[Path(cfg.input_path).parent], # You can also track previous stages
        runlock_path=Path(cfg.save_dir) / 'run.lock'
    )
```

Now, running `process()` will generate a `results/process/run.lock` file, giving you a complete snapshot of your run.

### Step 2: Log to MLflow with `mlflow_lock`

Logging to MLflow is isolated in a separate context manager. This decouples your core logic from your logging logic, which is useful for adding diagnostics later without re-running the entire experiment.

```python
# log.py
from pathlib import Path
import mlflow
from naga import mlflow_lock

def log_run(save_dir):
    """
    Logs the results of a run to MLflow.
    Can be run independently from the main process.
    """
    with mlflow_lock(save_dir) as run:
        # This creates a new MLflow run and links it to your run directory.
        # It automatically logs the contents of run.lock.
        # It also deprecates older MLflow runs for the same save_dir.

        # You can add custom logging here:
        mlflow.log_artifact(str(Path(save_dir) / 'out.txt'))
        print(f"Logged artifacts for run: {run.info.run_id}")

if __name__ == '__main__':
    # Assuming process() has already been run
    log_run('results/process')
```

### Step 3: Create a Powerful CLI with `clicfg`

The `@naga.clicfg` decorator turns your configuration class into a flexible command-line interface.

```python
# process.py
...
from naga import clicfg

@clicfg(config_class=Config)
def main(cfg: Config):
    """Main entry point for the process."""
    process(cfg)

if __name__ == '__main__':
    main()
```

This simple addition unlocks a powerful CLI:

```bash
# Run with default config
python process.py

# Override a parameter
python process.py -o param=10

# Provide a different config file
python process.py --config conf/my_config.yml

# Load a specific experiment from a multi-stage config file
python process.py --config conf/multi_stage.yml --experiment process_v2

# Run multiple experiments in parallel
echo "1\n2\n3" > tasks.txt
python process.py --tasks tasks.txt --task_to param --n_jobs=3
```

## Development Workflow: The Debug Decorator

When developing, you often want the script to drop into an interactive debugger on failure. The `@unsafe_debug` decorator provides this behavior.

```python
# process.py
...
from naga import clicfg, unsafe_debug

@unsafe_debug
@clicfg(config_class=Config)
def main(cfg: Config):
    a = 0
    b = 1 / a  # This will raise an exception
    process(cfg)

if __name__ == '__main__':
    main()
```

Now, run the function in a python/jupyter repl environment with the `NAGA_DEBUG=1` environment variable. When the exception occurs,  all the local variables (`cfg`, `a`, etc.) will be available for interactive inspection.

```bash
NAGA_DEBUG=1 ipython -i process.py
# ... Exception occurs ...
# Dropping into an interactive shell.
# The current context is available in the `ctx` dictionary.
# For example, access the config with `ctx['cfg']`.
IPython post-mortem debugger> a
0
```
This workflow combines the best of both worlds: the exploratory power of a notebook and the robustness of a script.
