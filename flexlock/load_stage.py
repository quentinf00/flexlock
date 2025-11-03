"""Utility for loading data from a previous FlexLock stage."""

from pathlib import Path
import yaml


def load_stage_from_path(path: str) -> dict:
    """
    Loads a stage from a given path and returns its flattened data, including
    all its ancestors.

    Args:
        path (str): The path to the directory of the previous stage.

    Returns:
        dict: A flattened, deduplicated dictionary of all ancestor runs.
    """
    all_stages = {}
    _load_and_flatten_recursively(Path(path).as_posix(), path, all_stages)
    return all_stages


def _load_and_flatten_recursively(
    stage_key: str, stage_path_str: str, all_stages: dict
):
    """
    Recursively loads a stage and its ancestors, adding them to the all_stages dict.
    """
    # Use the canonical path as the key to prevent duplicates
    canonical_key = Path(stage_path_str).resolve().name
    if canonical_key in all_stages:
        return

    stage_path = Path(stage_path_str)
    lock_file = stage_path / "run.lock"

    if not lock_file.exists():
        raise FileNotFoundError(
            f"run.lock not found in previous stage '{stage_key}': {lock_file}"
        )

    with open(lock_file, "r") as f:
        stage_data = yaml.safe_load(f)

    # Recurse into nested stages first (depth-first)
    if "prevs" in stage_data:
        for nested_key, nested_data in stage_data["prevs"].items():
            nested_path = nested_data.get("config", {}).get("save_dir")
            if not nested_path:
                raise ValueError(
                    f"Could not find 'config.save_dir' in nested stage '{nested_key}' from '{stage_key}'"
                )
            _load_and_flatten_recursively(nested_key, nested_path, all_stages)

    # Add the current stage's data (without its own lineage) to the dict
    stage_data.pop("prevs", None)
    all_stages[canonical_key] = stage_data
