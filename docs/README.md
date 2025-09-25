# Naga Library Documentation

## Overview

Naga is a Python library designed to improve the quality of life when developing ML experiments. It provides a set of decorators and utilities that address common requirements in ML development:

1. **Easy debugging when scripting**: Supports interactive development with IDEs like VSCode and Jupyter
2. **Seamless transition from scripts to functions**: No cost transition going from script to library function
3. **Easy exploration of different configurations**: Lightweight config management
4. **Automatic versioning of data and source code**: Ensures reproducibility
5. **Saving and restoring experiments**: Track and restore experiment states
6. **Browsing and comparing results across runs**: Compare different experiment runs
7. **From simple case scripting to parallel execution**: Scale from single to parallel execution

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Decorators](./decorators.md)
4. [Usage Examples](./examples.md)
5. [MLflow Integration](#mlflow-integration)
6. [Diagnostic Workflow](./DIAGNOSTIC_WORKFLOW.md)

## Installation

To install Naga, you can use pip:

```bash
pip install naga
```

Or if using the pixi package manager:

```bash
pixi add naga
```

## Quick Start

The recommended approach for using Naga is with the following script template that separates computation from diagnostics. For a more detailed explanation of this workflow, see the [Diagnostic Workflow](./DIAGNOSTIC_WORKFLOW.md) page.

```python
<my_stage.py>
from dataclasses import dataclass
from omegaconf import OmegaConf
from pathlib import Path
from datetime import datetime
from naga import clicfg, snapshot, runlock, track_data
from naga.mlflow_log import mlflow_log_run

# Register a resolver for automatic timestamp formatting
OmegaConf.register_resolver('now', lambda s: datetime.now().strftime(s), replace=True)

@dataclass
class Config:
    save_dir = "results/<my_stage>/${now:%y%m%d-%H%M}"
    param = 1
    # All the parameters for the function go here

@runlock
@snapshot(branch="run_logs", message="Naga experiment run")
@track_data("input_data")
@clicfg
def main(cfg: Config = OmegaConf.structured(Config())):
    try: 
        # %% The percent cell allows for interactive execution in IDEs like VSCode or Jupyter console
        save_dir = Path(cfg.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        OmegaConf.resolve(cfg)
        OmegaConf.save(cfg, save_dir / 'config.yaml')  # Save config

        # %%
        print(cfg.param)
        # Your main computation logic here
        # ...
        
    except Exception as e:  # Catch errors when executing full function
        import traceback
        print(traceback.format_exc())  # Print traceback
    finally:
        return cfg  # Return cfg for diag function

@mlflow_log_run(
    run_lock_path=lambda cfg: Path(cfg.save_dir) / "run.lock",
    log_file_path=lambda cfg: Path(cfg.save_dir) / "experiment.log"
)
def diag(cfg):
    # Diagnostic and logging function - separate from computation
    # This allows you to iterate on diagnostics without recomputing
    save_dir = Path(cfg.save_dir)
    
    # You can load artifacts saved by main() and perform analysis
    # For example, loading a results file:
    # results = load_results(save_dir / "results.pkl")
    
    # Perform diagnostics and visualizations
    print(f"Analyzing results in {save_dir}")
    # ... diagnostic code ...
    
    # If using MLflow logging, this is where you would log metrics/artifacts
    # mlflow.log_metric("accuracy", value)

if __name__ == '__main__':
    # Run main computation
    cfg = main()
    
    # Then run diagnostics
    diag(cfg)
```

## Decorators

Naga provides several decorators to enhance your experiment workflow:

- **`@clicfg`**: Configuration management from CLI
- **`@snapshot`**: Automatic source code versioning
- **`@track_data`**: Data dependency tracking
- **`@runlock`**: State management with run.lock files
- **`@load_stage`**: Loading previous experiment stages

For detailed information about each decorator, see the [Decorators](./decorators.md) page.

## MLflow Integration

Naga provides seamless integration with MLflow for experiment tracking and logging. See our documentation on [MLflow Integration](./decorators.md#mlflow-integration) and our [Diagnostic Workflow](./DIAGNOSTIC_WORKFLOW.md) for more details.
