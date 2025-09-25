# Naga Decorators

Naga provides several decorators to enhance your experiment workflow. Each decorator addresses specific aspects of experiment management.

## The Unified `@naga` Decorator

For convenience, Naga provides a single `@naga` decorator that wraps all other decorators. This allows you to configure your entire experiment workflow with a single, clean decorator.

### Usage

```python
from naga import naga
from omegaconf import OmegaConf
from dataclasses import dataclass

@dataclass
class Config:
    save_dir: str = "results/my_experiment"
    input_data: str = "data/raw"
    param: int = 1

@naga(
    snapshot_params={'branch': 'unified-runs', 'message': 'Auto-snapshot from @naga'},
    track_data_params=['input_data']
)
def main(cfg: Config = OmegaConf.structured(Config())):
    print(f"Parameter value: {cfg.param}")
    print(f"Input data: {cfg.input_data}")
    print(f"Save directory: {cfg.save_dir}")

if __name__ == "__main__":
    main()
```

The `@naga` decorator takes the following parameters:
- `snapshot_params` (dict): A dictionary of parameters for the `@snapshot` decorator.
- `track_data_params` (list): A list of keys for the `@track_data` decorator.
- `load_stage_params` (list): A list of keys for the `@load_stage` decorator.
- `use_clicfg` (bool): Set to `False` to disable the `@clicfg` decorator.
- `use_runlock` (bool): Set to `False` to disable the `@runlock` decorator.
- `use_debug` (bool): Set to `False` to disable the `@unsafe_debug` decorator.

---

The following sections provide details on the individual decorators that `@naga` combines.

## Configuration Management: `@clicfg`

The `@clicfg` decorator provides CLI configuration capabilities using OmegaConf, allowing you to specify a base config, overrides, and an experiment key.

### Basic Usage

```python
from omegaconf import OmegaConf
from dataclasses import dataclass
from naga import clicfg

@dataclass
class Config:
    save_dir: str = "results/my_experiment"
    param: int = 1

@clicfg
def main(cfg: Config = OmegaConf.structured(Config())):
    # Your experiment logic here
    print(f"Parameter value: {cfg.param}")
    print(f"Save directory: {cfg.save_dir}")

if __name__ == "__main__":
    main()
```

### Command-Line Usage

Once decorated with `@clicfg`, your function can be configured from the command line:

```bash
# Load a config from a file
python my_script.py --config path/to/config.yaml

# Override specific parameters
python my_script.py -o 'param=10' 'save_dir=/new/path'

# Use both a config file and overrides
python my_script.py --config config.yaml --overrides_path overrides.yaml -o 'param=new_value'

# Select a specific experiment from a config file
python my_script.py --config experiments.yaml --experiment exp1
```

The decorator intelligently ignores sys.argv when running in interactive environments like Jupyter notebooks.

## Source Code Versioning: `@snapshot`

The `@snapshot` decorator automatically versions your source code by taking a Git snapshot before running your function:

```python
from naga import snapshot

@snapshot(branch="run_logs", message="Naga: Auto-snapshot", 
          include=["*.py", "*.yaml"], exclude=["*.log", "tmp/"])
def my_experiment():
    # Your experiment logic here
    pass
```

### Parameters

- `branch`: The git branch to commit to (default: "run_logs")
- `message`: The commit message (default: "Naga: Auto-snapshot")
- `include`: List of glob patterns to include (optional)
- `exclude`: List of glob patterns to exclude (optional)

The decorator stores the commit hash in the run context for later use in the `run.lock` file.

## Data Versioning: `@track_data`

The `@track_data` decorator computes and tracks hashes of data dependencies specified in your configuration:

```python
from naga import track_data

@track_data("data_dir", "input_file", "preprocessing_params.config_path")
def process_data(cfg):
    # Your data processing logic here
    pass
```

The decorator takes one or more dot-separated keys in the OmegaConf object that point to file or directory paths to be hashed. These hashes are stored in the run context and included in the `run.lock` file.

## State Management: `@runlock`

The `@runlock` decorator manages the state of a run by creating a `run.lock` file that contains all relevant information:

```python
from naga import runlock

@runlock
def main(cfg):
    # Your main logic here
    pass
```

The decorator should be placed *before* the `@clicfg` decorator so it can access the final, resolved configuration object. It gathers information from the run context (like git commits from `@snapshot` and data hashes from `@track_data`) and saves it to `cfg.save_dir / 'run.lock'`.

The `run.lock` file contains:
- The resolved configuration
- Git commit hash (if `@snapshot` was used)
- Data hashes (if `@track_data` was used)
- Previous stage information (if `@load_stage` was used)

## Loading Previous Stages: `@load_stage`

The `@load_stage` decorator loads the `run.lock` files from previous experiment stages:

```python
@load_stage("previous_stage_path", "another_stage_path")
def main(cfg):
    # Your main logic that uses previous stage data
    pass
```

This decorator takes one or more keys that point to previous stage directories in your config. It recursively loads all dependencies and creates a flattened, deduplicated view of all ancestor runs, making them available in the run context.

## Debugging: `@unsafe_debug`

The `@unsafe_debug` decorator is a utility for post-mortem debugging. When a function decorated with it raises an exception, it injects the function's local variables into the caller's scope, allowing you to inspect the state of the failed function.

**Warning:** This is an advanced and potentially dangerous pattern. Modifying a caller's local scope can lead to unpredictable behavior and is intended for debugging purposes only.

This decorator is **only active** if the environment variable `NAGA_DEBUG` is set to `1` or `true`.

### Usage

```python
import os
from naga import unsafe_debug

# Activate the decorator by setting the environment variable
os.environ['NAGA_DEBUG'] = '1'

@unsafe_debug
def failing_function(a, b):
    numerator = a + b
    denominator = a - b
    result = numerator / denominator  # This will raise a ZeroDivisionError
    return result

try:
    failing_function(10, 10)
except ZeroDivisionError:
    print("Caught the expected exception.")

# Now you can inspect the local variables from the failed function
print(f"Value of 'numerator': {numerator}")
print(f"Value of 'denominator': {denominator}")

# Clean up the environment variable
del os.environ['NAGA_DEBUG']
```

When the exception occurs, `@unsafe_debug` will print the exception and the local variables to stderr and then inject them into the scope where the function was called. This allows you to interactively debug the state that caused the error.

## Complete Workflow Example

Here's how to combine all decorators for a complete experiment with separate main and diagnostic functions:

```python
from dataclasses import dataclass
from omegaconf import OmegaConf
from pathlib import Path
from datetime import datetime
import os

from naga import clicfg, snapshot, runlock, track_data, load_stage

# Register a resolver for automatic timestamp formatting
OmegaConf.register_resolver('now', lambda s: datetime.now().strftime(s), replace=True)

@dataclass
class Config:
    save_dir: str = "results/preprocessing/${now:%y%m%d-%H%M}"
    input_data: str = "data/raw"
    output_data: str = "data/processed"
    param: int = 1
    previous_stage_dir: str = "results/previous_stage/240101-1000"

# Order of decorators matters: runlock first to capture final config
@runlock
@snapshot(branch="run_logs", message="Preprocessing experiment", 
          exclude=["*.log", "tmp/", "__pycache__"])
@track_data("input_data", "output_data")
@clicfg
def main(cfg = OmegaConf.structured(Config())):
    try:
        # Main experiment logic
        save_dir = Path(cfg.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Processing with parameter: {cfg.param}")
        print(f"Input data: {cfg.input_data}")
        print(f"Output data: {cfg.output_data}")
        
        # Your actual experiment code here
        # Save any results that will be used by diag function
        # ...
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
    finally:
        return cfg, locals()

def diag(cfg):
    # Diagnostic and analysis function - separate from computation
    # This allows you to iterate on diagnostics without recomputing
    save_dir = Path(cfg.save_dir)
    
    # Load results saved by main() and perform analysis
    print(f"Analyzing results in {save_dir}")
    # ... diagnostic code ...
    
if __name__ == '__main__':
    cfg, local_vars = main()
    diag(cfg)
```

## MLflow Integration

Naga provides MLflow integration for experiment tracking and logging. For a detailed explanation of the recommended workflow, please see our [Diagnostics and Logging Workflow](./DIAGNOSTIC_WORKFLOW.md) guide.

### MLflow Logging Decorator

```python
from pathlib import Path
from naga.mlflow_log import mlflow_log_run

@mlflow_log_run(run_lock_path=Path("results/my_experiment/run.lock"), 
                log_file_path=Path("results/my_experiment/experiment.log"))
def my_experiment(cfg):
    # Your experiment logic here
    pass
```

This decorator:
- Logs parameters from the `run.lock` file
- Logs artifacts like log files
- Sets tags to identify runs and handle deprecation of previous runs
- Can resume existing runs with the same logical identifier

### Updating Past MLflow Runs

You can update MLflow logs for previously executed runs:

```python
from pathlib import Path
from naga.update_mlflow_runs import update_mlflow_run_from_experiment_dir

# Update a single run
update_mlflow_run_from_experiment_dir(Path("results/my_old_experiment"))

# Process multiple runs
import glob
for exp_dir in glob.glob("results/my_stage_*"):
    update_mlflow_run_from_experiment_dir(Path(exp_dir))
```