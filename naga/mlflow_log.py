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
def mlflow_lock(path: str, runlock_file: str = 'run.lock', log_file: str = 'experiment.log'):
    """
    A context manager to handle the MLflow run lifecycle.

    It uses the provided `path` as a logical run identifier to manage and deprecate
    previous runs. Upon exiting, it logs the `run.lock` and `experiment.log` files.

    Args:
        path (str): The directory of the run, used as the logical run identifier.
        runlock_file (str, optional): Name of the runlock file. Defaults to 'run.lock'.
        log_file (str, optional): Name of the log file. Defaults to 'experiment.log'.
    """
    logical_run_identifier = Path(path).as_posix()
    run_lock_path = Path(path) / runlock_file
    log_file_path = Path(path) / log_file

    # --- Search for previous active run ---
    previous_active_run_id = None
    try:
        runs = mlflow.search_runs(
            filter_string=f"tags.`naga.logical_run_id` = '{logical_run_identifier}' AND tags.`naga.run_status` = 'active'",
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
            
            mlflow.set_tag("naga.logical_run_id", logical_run_identifier)
            mlflow.set_tag("naga.run_status", "active")
            if previous_active_run_id:
                mlflow.set_tag("naga.supersedes_run_id", previous_active_run_id)

            yield active_run

    finally:
        # --- Exit the run context ---
        if current_run_id: # Ensure we only log if the run was successfully started
            # Log parameters and artifacts
            if run_lock_path.exists():
                with open(run_lock_path, "r") as f:
                    run_lock_data = yaml.safe_load(f)
                
                if run_lock_data and "config" in run_lock_data:
                    config_dict = OmegaConf.create(run_lock_data["config"])
                    flat_params = pd.json_normalize(
                        OmegaConf.to_container(config_dict, resolve=True), sep='.'
                    ).to_dict(orient="records")[0]
                    mlflow.log_params(flat_params)
                    logger.info(f"Logged parameters from {run_lock_path}")
                
                mlflow.log_artifact(str(run_lock_path))
                logger.info(f"Logged artifact: {run_lock_path}")

            if log_file_path.exists():
                mlflow.log_artifact(str(log_file_path))
                logger.info(f"Logged artifact: {log_file_path}")

        # Deprecate the old run if a new one was successfully created
        if previous_active_run_id and current_run_id:
            try:
                with mlflow.start_run(run_id=previous_active_run_id):
                    mlflow.set_tag("naga.run_status", "deprecated")
                    mlflow.set_tag("naga.superseded_by_run_id", current_run_id)
                    logger.info(f"Deprecated previous run {previous_active_run_id}")
            except Exception as e:
                logger.error(f"Failed to deprecate previous run {previous_active_run_id}: {e}")
