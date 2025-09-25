
# Naga Diagnostics and Logging Workflow

This document outlines the recommended workflow for using the Naga library for diagnostics and logging, particularly with MLflow. The core principle of Naga is the **separation of computation from diagnostics**. This separation allows you to iterate on your logging, analysis, and visualizations without re-running expensive computations.

## The Core Idea: `main` and `diag`

The recommended structure for a Naga-based experiment is to have two main functions:

1.  `main()`: This function contains your core computation logic (e.g., data preprocessing, model training, evaluation). It should be decorated with the necessary Naga decorators to capture the experiment's state (`@runlock`, `@snapshot`, `@track_data`, `@clicfg`). At the end of its execution, it saves its results to disk and creates a `run.lock` file that contains all the metadata for the run.

2.  `diag()`: This function is responsible for all diagnostics, analysis, and logging. It loads the results saved by `main()` and uses the information in the `run.lock` file to log the experiment to MLflow. This function is decorated with `@mlflow_log_run`.

The `run.lock` file acts as the bridge between `main` and `diag`. It contains everything needed to reproduce and understand the run, including the full configuration, git commit hashes, and data hashes.

## Why Separate Computation from Diagnostics?

-   **Efficiency**: You can change your logging, add new plots, or fix a metric calculation in your `diag` function and re-run it without having to wait for the `main` function to execute again.
-   **Clarity**: It keeps your code clean and organized. The `main` function focuses on the science, and the `diag` function focuses on the bookkeeping.
-   **Reproducibility**: The `run.lock` file ensures that the diagnostics are always based on the exact same configuration and context as the computation.

## The Complete Workflow: An Example

Here is a complete example that demonstrates the recommended workflow.

```python
# my_experiment.py

from dataclasses import dataclass
from omegaconf import OmegaConf
from pathlib import Path
from datetime import datetime
import os

from naga import clicfg, snapshot, runlock, track_data
from naga.mlflow_log import mlflow_log_run

# 1. Register a resolver for automatic timestamp formatting
OmegaConf.register_resolver('now', lambda s: datetime.now().strftime(s), replace=True)

# 2. Define your configuration as a dataclass
@dataclass
class Config:
    save_dir: str = "results/my_experiment/${now:%y%m%d-%H%M}"
    input_data: str = "data/raw.csv"
    learning_rate: float = 0.01
    epochs: int = 10

# 3. Create the `main` function with the core logic
#    Order of decorators matters: @runlock should be first to capture the final config.
@runlock
@snapshot(branch="run_logs", message="Naga experiment run")
@track_data("input_data")
@clicfg
def main(cfg: Config = OmegaConf.structured(Config)):
    try:
        # Your main experiment logic goes here
        save_dir = Path(cfg.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Running experiment with learning rate: {cfg.learning_rate}")
        
        # In a real experiment, you would do something like:
        # model = train_model(cfg.input_data, cfg.learning_rate, cfg.epochs)
        # save_model(model, save_dir / "model.pkl")
        # save_metrics({"accuracy": 0.95}, save_dir / "metrics.json")
        
        # For this example, we'll just create some dummy files
        (save_dir / "model.pkl").write_text("dummy model")
        (save_dir / "metrics.json").write_text('{"accuracy": 0.95}')
        (save_dir / "experiment.log").write_text("Log content from the experiment.")

    except Exception as e:
        import traceback
        print(traceback.format_exc())
    finally:
        # Return the config for the diag function
        return cfg

# 4. Create the `diag` function for logging and analysis
#    It is decorated with @mlflow_log_run
@mlflow_log_run(
    run_lock_path=lambda cfg: Path(cfg.save_dir) / "run.lock",
    log_file_path=lambda cfg: Path(cfg.save_dir) / "experiment.log"
)
def diag(cfg: Config):
    # This function is for diagnostics and logging.
    # It loads artifacts and logs them to MLflow.
    save_dir = Path(cfg.save_dir)
    
    print(f"Running diagnostics for experiment in {save_dir}")
    
    # In a real scenario, you would load metrics and log them
    # with open(save_dir / "metrics.json", "r") as f:
    #     metrics = json.load(f)
    # mlflow.log_metrics(metrics)
    
    # You can also log other artifacts
    # mlflow.log_artifact(save_dir / "model.pkl")

# 5. Run the workflow
if __name__ == '__main__':
    # First, run the main computation
    cfg = main()
    
    # Then, run the diagnostics and logging
    diag(cfg)
```

## Logical Run Management in MLflow

A key feature of `@mlflow_log_run` is its ability to manage the history of an experiment. It uses the `save_dir` from your configuration as a **logical run identifier**.

When you run `diag` for the first time for a given `save_dir`, Naga creates a new MLflow run and adds the following tags:
-   `naga.logical_run_id`: The `save_dir` of the experiment.
-   `naga.run_status`: `active`

If you later modify your `diag` function (e.g., to log a new metric) and re-run it with the same `cfg`, Naga will:
1.  Create a **new** MLflow run with the updated information.
2.  Tag the new run as `active`.
3.  Find the previous run with the same `logical_run_id`, and change its status to `deprecated`.
4.  Add tags to link the old and new runs (`naga.supersedes_run_id` and `naga.superseded_by_run_id`).

This creates a clean and clear history in MLflow, where only the latest version of the diagnostics for a given experiment is marked as "active".

## Updating Existing Documentation

To ensure consistency, the main `README.md` and `decorators.md` should be updated to reflect this clarified workflow. The "Quick Start" section in the `README.md` should be updated to include the `@mlflow_log_run` decorator on the `diag` function, and the "MLflow Integration" section in `decorators.md` should link to this document for a more detailed explanation.
