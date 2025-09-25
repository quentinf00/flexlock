import functools
import logging
import os
from pathlib import Path
import pandas as pd
from typing import Union, Callable, Any

import mlflow
import yaml
from omegaconf import OmegaConf

logger = logging.getLogger(__name__)

def mlflow_log_run(run_lock_path: Union[Path, Callable, str], log_file_path: Union[Path, Callable, str, None] = None):
    """
    A decorator to integrate MLflow logging with a function execution.
    It logs parameters from a run.lock file and optionally an experiment log file.
    It can also resume an existing MLflow run.

    Args:
        run_lock_path: The path to the run.lock file, or a function that takes 
                      the config as an argument and returns the path,
                      or a string path that can be formatted with the config.
        log_file_path: Optional path to an experiment log file to be logged as an artifact,
                      or a function that takes the config as an argument and returns the path,
                      or a string path that can be formatted with the config.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get config from the function arguments (first argument should be cfg or save_dir)
            if not args:
                logger.warning("No arguments provided to function, cannot proceed with MLflow logging.")
                return func(*args, **kwargs)
            
            # Handle both config objects and save_dir paths
            first_arg = args[0]
            if hasattr(first_arg, 'save_dir'):  # It's a config object
                cfg = first_arg
                save_dir = Path(cfg.save_dir)
            else:  # It's likely a save_dir path
                save_dir = Path(first_arg)
                # Try to load config from the save_dir
                try:
                    config_path = save_dir / 'config.yaml'
                    if config_path.exists():
                        cfg = OmegaConf.load(config_path)
                    else:
                        # If no config file, create empty config with save_dir
                        cfg = OmegaConf.create({"save_dir": str(save_dir)})
                except Exception as e:
                    logger.warning(f"Could not load config from save_dir {save_dir}: {e}")
                    cfg = OmegaConf.create({"save_dir": str(save_dir)})

            # Resolve the run_lock_path based on whether it's a function, string or Path
            if callable(run_lock_path):
                actual_run_lock_path = run_lock_path(cfg)
            elif isinstance(run_lock_path, str):
                # Format the string with config values if possible
                try:
                    actual_run_lock_path = Path(run_lock_path.format(save_dir=cfg.save_dir))
                except:
                    actual_run_lock_path = Path(run_lock_path)
            else:
                actual_run_lock_path = run_lock_path

            # Resolve the log_file_path based on whether it's a function, string or Path
            actual_log_file_path = None
            if log_file_path is not None:
                if callable(log_file_path):
                    actual_log_file_path = log_file_path(cfg)
                elif isinstance(log_file_path, str):
                    # Format the string with config values if possible
                    try:
                        actual_log_file_path = Path(log_file_path.format(save_dir=cfg.save_dir))
                    except:
                        actual_log_file_path = Path(log_file_path)
                else:
                    actual_log_file_path = log_file_path

            run_id = os.environ.get("MLFLOW_RUN_ID")
            print(f"{run_id=}")

            run_lock_data = None
            logical_run_identifier = None
            if actual_run_lock_path.exists():
                with open(actual_run_lock_path, "r") as f:
                    run_lock_data = yaml.safe_load(f)
                print(run_lock_data)
                if "config" in run_lock_data and "save_dir" in run_lock_data["config"]:
                    logical_run_identifier = run_lock_data["config"]["save_dir"]
                    logger.info(f"Derived logical_run_identifier from save_dir: {logical_run_identifier}")
                else:
                    logger.warning(f"'config' or 'save_dir' section not found in {actual_run_lock_path}. Cannot derive logical_run_identifier.")
            else:
                logger.warning(f"run.lock file not found at {actual_run_lock_path}. Cannot derive logical_run_identifier.")

            previous_active_run_id = None
            if logical_run_identifier:
                # Search for previous active runs with the same logical identifier
                # We use a custom tag 'naga.logical_run_id' to group them
                runs = mlflow.search_runs(
                    filter_string=f"tags.`naga.logical_run_id` = '{logical_run_identifier}' AND tags.`naga.run_status` = 'active'",
                    order_by=["start_time DESC"],
                    max_results=1
                )
                if runs.empty:
                    logger.info(f"No previous active run found for logical_run_identifier: {logical_run_identifier}")
                else:
                    # Check if the save_dir from the previous run matches the current one
                    previous_run = mlflow.get_run(runs.iloc[0].run_id)
                    if previous_run.data.tags.get('naga.logical_run_id') == logical_run_identifier:
                        previous_active_run_id = runs.iloc[0].run_id
                        logger.info(f"Found previous active run for {logical_run_identifier}: {previous_active_run_id}")
                    else:
                        logger.info(f"Found previous active run with a different save_dir. A new run will be created.")

            with mlflow.start_run(run_id=run_id) as active_run:
                current_run_id = active_run.info.run_id
                logger.info(f"MLflow Run ID: {current_run_id}")
                print(f"MLflow Run ID: {current_run_id}")

                if logical_run_identifier:
                    mlflow.set_tag("naga.logical_run_id", logical_run_identifier)
                    mlflow.set_tag("naga.run_status", "active")
                    if previous_active_run_id:
                        mlflow.set_tag("naga.supersedes_run_id", previous_active_run_id)
                        logger.info(f"New run {current_run_id} supersedes run {previous_active_run_id}")

                # Log parameters from run.lock
                if run_lock_data and "config" in run_lock_data:
                    # Convert config to a flat dictionary for MLflow logging
                    config_dict = OmegaConf.create(run_lock_data["config"])
                    mlflow.log_params(
                        pd.json_normalize(
                            OmegaConf.to_container(config_dict, resolve=True),
                            sep='.',
                        ).to_dict(orient="records")[0]
                    )
                    logger.info(f"Logged parameters from {actual_run_lock_path}")
                else:
                    logger.warning(f"'config' section not found in {actual_run_lock_path} or run_lock_data is None. Parameters not logged.")

                # Log logfile if exists
                if actual_log_file_path and actual_log_file_path.exists():
                    mlflow.log_artifact(str(actual_log_file_path))
                    print(f"Logged artifact: {actual_log_file_path}")
                    logger.info(f"Logged artifact: {actual_log_file_path}")
                elif actual_log_file_path:
                    logger.warning(f"Log file not found at {actual_log_file_path}")

                result = func(*args, **kwargs)

            # After the new run is finished, deprecate the previous one if it exists
            if logical_run_identifier and previous_active_run_id:
                with mlflow.start_run(run_id=previous_active_run_id) as old_run:
                    mlflow.set_tag("naga.run_status", "deprecated")
                    mlflow.set_tag("naga.superseded_by_run_id", current_run_id)
                    logger.info(f"Deprecated previous run {previous_active_run_id} and linked to new run {current_run_id}")

            return result

        return wrapper

    return decorator
