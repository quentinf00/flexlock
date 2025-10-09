import logging
import os
from pathlib import Path
import mlflow
import yaml
from omegaconf import OmegaConf
import pandas as pd
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@contextmanager
def mlflowlink(path: str, snapshot_file: str = 'run.lock', log_file: str = 'experiment.log'):
    """
    A context manager to handle the MLflow run lifecycle.

    It uses the provided `path` as a logical run identifier to manage and deprecate
    previous runs. Upon exiting, it logs the `run.lock` and `experiment.log` files.

    Args:
        path (str): The directory of the run, used as the logical run identifier.
        snapshot_file (str, optional): Name of the snapshot file. Defaults to 'run.lock'.
        log_file (str, optional): Name of the log file. Defaults to 'experiment.log'.
    """
    logical_run_identifier = Path(path).as_posix()
    run_lock_path = Path(path) / snapshot_file
    log_file_path = Path(path) / log_file

    # --- Search for previous active run ---
    previous_active_run_id = None
    try:
        runs = mlflow.search_runs(
            filter_string=f"tags.`flexlock.logical_run_id` = '{logical_run_identifier}' AND tags.`flexlock.run_status` = 'active'",
            order_by=["start_time DESC"],
            max_results=1
        )
        if not runs.empty:
            previous_active_run_id = runs.iloc[0].run_id
            logger.info(f"Found previous active run for {logical_run_identifier}: {previous_active_run_id}")
    except Exception as e:
        logger.warning(f"Could not search for MLflow runs: {e}")


    # --- Enter the new run context ---
    current_run_id = None
    try:
        with mlflow.start_run() as active_run:
            current_run_id = active_run.info.run_id
            logger.info(f"Started new MLflow run {current_run_id} for {logical_run_identifier}")
            
            mlflow.set_tag("flexlock.logical_run_id", logical_run_identifier)
            mlflow.set_tag("flexlock.run_status", "active")
            if previous_active_run_id:
                mlflow.set_tag("flexlock.supersedes_run_id", previous_active_run_id)

            yield active_run

    finally:
        # --- Exit the run context ---

        if current_run_id: # Ensure we only log if the run was successfully started
            # Log parameters and artifacts
            if run_lock_path.exists():
                
                config_dict = OmegaConf.load(run_lock_path)
                flat_params = pd.json_normalize(
                    OmegaConf.to_container(config_dict, resolve=True), sep='.'
                ).to_dict(orient="records")[0]
                mlflow.log_params(flat_params, run_id=current_run_id)
                logger.info(f"Logged parameters from {run_lock_path}")
                
                mlflow.log_artifact(str(run_lock_path), run_id=current_run_id)
                logger.info(f"Logged artifact: {run_lock_path}")
                print(f"Logged artifact: {run_lock_path}")

            if log_file_path.exists():
                print(f"Logged log: {log_file_path}")
                mlflow.log_artifact(str(log_file_path), run_id=current_run_id)
                logger.info(f"Logged artifact: {log_file_path}")

        # Deprecate the old run if a new one was successfully created
        if previous_active_run_id and current_run_id:
            try:
                with mlflow.start_run(run_id=previous_active_run_id):
                    mlflow.set_tag("flexlock.run_status", "deprecated")
                    mlflow.set_tag("flexlock.superseded_by_run_id", current_run_id)
                    logger.info(f"Deprecated previous run {previous_active_run_id}")
            except Exception as e:
                logger.error(f"Failed to deprecate previous run {previous_active_run_id}: {e}")
                raise e
