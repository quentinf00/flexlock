"""MLflow integration for FlexLock."""

import os
from pathlib import Path
from typing import Dict, Optional, Any
from contextlib import contextmanager
from loguru import logger
from omegaconf import OmegaConf


def _flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flatten a nested dictionary into a single-level dict with dot-separated keys."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


@contextmanager
def mlflow_context(
    save_dir: str | Path,
    experiment_name: str = os.environ.get('MLFLOW_EXPERIMENT_NAME', "Default"),
    run_name: str = None,
    tags: Dict[str, str] = None,
    log_config: bool = True,
    log_artifacts: bool = True,
):
    """
    Manages a "Shadow Run" in MLflow linked to a physical directory.

    This context manager implements the "Always New + Deprecate Old" strategy,
    treating the MLflow Run as a temporary view of the persistent physical state
    (the save_dir).

    Behavior:
    1. SEARCH: Finds the currently 'active' run for this directory.
    2. CREATE: Starts a completely new run.
    3. INHERIT: Logs existing config/artifacts found in save_dir to the new run.
    4. INHERIT TAGS: Copies user tags (e.g., pipeline tags) from previous run.
    5. SWAP: Marks new run 'active', marks old run 'deprecated'.

    Args:
        save_dir: The directory containing the run data (e.g., outputs/exp/run_01)
        experiment_name: MLflow experiment name (default: "Default")
        run_name: Name for this MLflow run (default: save_dir.name)
        tags: Additional tags to add to the run (overrides inherited tags)
        log_config: If True, logs parameters from run.lock file
        log_artifacts: If True, logs standard artifacts (logs, lock file)

    Yields:
        mlflow.ActiveRun: The active MLflow run object, or None if MLflow not available

    Note:
        User tags (not starting with 'flexlock.' or 'mlflow.') are automatically
        inherited from the previous active run. This is useful for pipeline workflows
        where you want tags like 'pipeline_run=xyz' to persist across stages.
        Explicitly passing a tag via the `tags` parameter will override the inherited value.

    Example:
        >>> # Stage 1: Train (creates run with pipeline tag)
        >>> with mlflow_context(save_dir, tags={"pipeline_run": "run_001"}):
        ...     mlflow.log_metric("train_loss", 0.32)
        ...
        >>> # Stage 2: Evaluate (inherits pipeline_run tag automatically)
        >>> with mlflow_context(save_dir):  # pipeline_run=run_001 inherited!
        ...     mlflow.log_metric("test_accuracy", 0.95)
    """
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except ImportError:
        logger.warning("MLflow not installed. To use mlflow_context, install with: pip install mlflow")
        yield None
        return

    save_dir = Path(save_dir).resolve()
    logical_id = save_dir.as_posix()
    client = MlflowClient()

    # Ensure Experiment Exists
    mlflow.set_experiment(experiment_name)
    exp = client.get_experiment_by_name(experiment_name)

    # 1. FIND PREVIOUS ACTIVE RUN
    # We look for runs pointing to this directory that are currently active
    prev_run_id = None
    prev_run_tags = {}
    try:
        filter_str = f"tags.`flexlock.dir` = '{logical_id}' AND tags.`flexlock.status` = 'active'"
        runs = client.search_runs(
            experiment_ids=[exp.experiment_id],
            filter_string=filter_str,
            max_results=1,
            order_by=["start_time DESC"]
        )
        if runs:
            prev_run_id = runs[0].info.run_id
            # Get the previous run's tags to inherit user tags (like pipeline tags)
            prev_run = client.get_run(prev_run_id)
            prev_run_tags = {
                k: v for k, v in prev_run.data.tags.items()
                if not k.startswith('flexlock.') and not k.startswith('mlflow.')
            }
            logger.info(f"Found previous active run: {prev_run_id}")
            if prev_run_tags:
                logger.debug(f"Inheriting tags from previous run: {prev_run_tags}")
    except Exception as e:
        logger.debug(f"No previous run found or search failed: {e}")

    # 2. START NEW RUN
    # Always a fresh ID
    run = mlflow.start_run(run_name=run_name or save_dir.name)
    run_id = run.info.run_id
    logger.info(f"Started new MLflow run {run_id} for {logical_id}")

    try:
        # 3. SET METADATA
        default_tags = {
            "flexlock.dir": logical_id,
            "flexlock.status": "active",  # It claims the throne immediately
        }
        if prev_run_id:
            default_tags["flexlock.supersedes"] = prev_run_id

        # Inherit user tags from previous run (e.g., pipeline tags)
        # These act as defaults that can be overridden by explicit tags parameter
        inherited_and_current_tags = {**prev_run_tags, **(tags or {})}
        default_tags.update(inherited_and_current_tags)

        mlflow.set_tags(default_tags)

        # 4. INHERIT STATE (Pull forward artifacts from disk)
        # This solves the "Empty Run" problem. Even if this is just a plotting script,
        # we log the run.lock and logs from the folder so this run looks complete.
        if log_config:
            lock_path = save_dir / "run.lock"
            if lock_path.exists():
                try:
                    # Log Config Params
                    cfg_obj = OmegaConf.load(lock_path)
                    content = cfg_obj.get("config", cfg_obj)  # Handle nested or flat
                    flat_params = _flatten_dict(OmegaConf.to_container(content, resolve=True))

                    # Sanitize (truncate long strings to avoid MLflow param length limits)
                    clean_params = {k: str(v)[:250] for k, v in flat_params.items()}
                    mlflow.log_params(clean_params)
                    logger.info(f"Logged parameters from {lock_path}")

                    # Log the lock file itself
                    mlflow.log_artifact(str(lock_path))
                    logger.info(f"Logged artifact: {lock_path}")
                except Exception as e:
                    logger.warning(f"MLflow config logging warning: {e}")

        if log_artifacts:
            # Auto-log standard files if they exist on disk
            for fname in ["experiment.log", "stderr.log", "stdout.log"]:
                fpath = save_dir / fname
                if fpath.exists():
                    mlflow.log_artifact(str(fpath))
                    logger.info(f"Logged artifact: {fpath}")

        # Yield control to user code (to log metrics, plots, etc.)
        yield run

    except Exception:
        # If user code crashes, we let it fail normally
        raise

    finally:
        mlflow.end_run()

        # 5. DEPRECATE OLD RUN (The atomic swap)
        # Only do this if the new run finished successfully (reached this block)
        if prev_run_id:
            try:
                client.set_tag(prev_run_id, "flexlock.status", "deprecated")
                client.set_tag(prev_run_id, "flexlock.superseded_by", run_id)
                logger.info(f"Superseded previous MLflow run {prev_run_id}")
            except Exception as e:
                logger.warning(f"Failed to deprecate run {prev_run_id}: {e}")

