## Quickstart

Let's start with a simple data processing script.

```python
# process.py
from pathlib import Path
from loguru import logger

class Config:
    param = 1
    input_path = 'data/preprocess/input.csv'
    save_dir = 'results/${vinc:process}' # Used by flexlock: create a new results/process_000x at each run

def process(cfg: Config):
    logger.add(Path(cfg) / 'experiment.log') # Log to file
    
    logger.info(f"Running with param: {cfg.param}")
    # Core logic
    output_path = Path(cfg.save_dir) / 'out.txt'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        for _ in range(cfg.param):
            f.write(Path(cfg.input_path).read_text())
    logger.info(f"Output written to {output_path}")

if __name__ == '__main__':
    # Create dummy input if it doesn't exist
    Path('data/preprocess/input.csv').parent.mkdir(parents=True, exist_ok=True)
    Path('data/preprocess/input.csv').write_text("some data")
    process(Config())
```

This is a standard Python script. Now, let's introduce FlexLock to add reproducibility and a powerful CLI.

### Step 1: Create a Powerful CLI with `flexcli`

The `@flexlock.flexcli` decorator turns your configuration class into a flexible command-line interface.

```python
# process.py
...
from flexlock import flexcli

@flexcli(config_class=Config)
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

# Run multiple experiments in parallel locally
echo "1\n2\n3" > tasks.txt
python process.py --tasks tasks.txt --task_to param --n_jobs=3

# Run multiple experiments in parallel in pbs or slurm
echo "1\n2\n3" > tasks.txt
python process.py --tasks tasks.txt --task_to param --pbs_config configs/pbs.yml
```

### Step 2: Track Your Run with `snapshot`

To ensure reproducibility, we need to track the configuration, code version, and data used in a run. `flexlock.snapshot` creates a `run.lock` file with this information.

```python
# process.py
...
from flexlock import snapshot

def process(cfg: Config=Config()):
    ...
    # Your core logic here...
    ...
    snapshot(
        config=cfg,
        repos=['.'],  # Track the git version of the current repo
        data=[cfg.input_path],  # Hash the input data
        # prevs=[Path(cfg.input_path).parent], # You can also track previous stages
    )
```

Now, running `process()` will generate a `results/process_000x/run.lock` file, giving you a complete snapshot of your run.

### Step 3 (Optional): Log to MLflow with `mlflowlink`
ML Flow can provide a dashboard to track and compare different runs and experiments

Logging to MLflow is isolated in a separate context manager. This decouples your core logic from your logging logic, which is useful for adding diagnostics later without re-running the entire experiment.

```python
# log.py
from pathlib import Path
import mlflow
from flexlock import mlflowlink

def log_run(save_dir):
    """
    Logs the results of a run to MLflow.
    Can be run independently from the main process.
    """
    with mlflowlink(save_dir) as run:
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



## Development Workflow: The Debug Decorator

When developing, you often want the script to drop into an interactive debugger on failure. The `@debug_on_fail` decorator provides this behavior.

```python
# process.py
...
from flexlock import flexcli, debug_on_fail

@flexcli(config_class=Config)
@debug_on_fail(stack_depth=3)
def main(cfg: Config):
    a = 0
    b = 1 / a  # This will raise an exception
    process(cfg)

if __name__ == '__main__':
    main()
```

Now, run the function in a python/jupyter repl environment with the `FLEXLOCK_DEBUG=1` environment variable. When the exception occurs,  all the local variables (`cfg`, `a`, etc.) will be available for interactive inspection.

```bash
FLEXLOCK_DEBUG=1 ipython -i process.py
----> 1 1/0

ZeroDivisionError: division by zero

In [1]:a
0
```
This workflow combines the best of both worlds: the exploratory power of a notebook and the robustness of a script.

NB: You can also decorate functions non top level function for the local context to bubble up 

