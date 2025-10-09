# `mlflowlink`: MLflow Integration

The `mlflowlink` context manager provides a robust and explicit way to manage the MLflow lifecycle for your experiments. It is designed to be separate from your core logic, allowing you to iterate on your logging and diagnostics without re-running your entire experiment.

## Philosophy

In FlexLock, we believe that your core scientific code should be decoupled from your MLOps tooling.

- **Core Logic**: A function that takes a configuration and produces outputs. It should be pure and testable.
- **Logging**: A separate function or script that takes the output directory of a run and logs its contents to a platform like MLflow.

This separation has several advantages:
- You can re-run your logging script to add new metrics or artifacts without the cost of re-running the experiment.
- You can log runs that were completed a long time ago.
- Your core logic remains clean and focused on its primary task.

## Basic Usage

The `mlflowlink` is a context manager that takes the path to a run directory (which should contain a `run.lock` file).

```python
# log.py
import mlflow
from flexlock import mlflowlink

def log_run(save_dir):
    """
    Logs the results of a completed run to MLflow.
    """
    with mlflowlink(save_dir) as run:
        # 1. A new MLflow run is created.
        # 2. The `run.lock` file from `save_dir` is automatically logged as an artifact.
        # 3. The MLflow run is tagged with a `logical_run_id` corresponding to `save_dir`.
        # 4. Any previous MLflow runs with the same `logical_run_id` are marked as "deprecated".

        print(f"MLflow run started with ID: {run.info.run_id}")

        # You can add any other logging here.
        # For example, log the output file as an artifact:
        mlflow.log_artifact(f"{save_dir}/out.txt")

        print("MLflow run finished.")

if __name__ == '__main__':
    # Assume the main process has already been run and created results in 'results/process'
    log_run('results/process')
```

## Logical Run Management

A key feature of `mlflowlink` is its management of "logical runs". Often, you will have multiple MLflow runs that correspond to the same conceptual experiment (e.g., you are re-running logging to add a new metric).

`mlflowlink` handles this by:
1.  Assigning a `logical_run_id` to each MLflow run, which is the absolute path of the `save_dir`.
2.  When a new run is created for a given `save_dir`, it finds all previous runs with the same `logical_run_id` and sets their status to `DEPRECATED`.
3.  It tags the new run with `status: active`.

This means you can easily filter for the "active" run for each of your experiments in the MLflow UI, giving you a clean and organized view of your results.
