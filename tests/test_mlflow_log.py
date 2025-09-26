import pytest
from unittest.mock import patch
import os
from pathlib import Path
import yaml
import mlflow
from mlflow.entities import ViewType
from omegaconf import OmegaConf


from naga.mlflow_log import mlflow_log_run

@pytest.fixture
def mlflow_tmp_uri(tmp_path):
    """Fixture to set up a temporary MLflow tracking URI."""
    tracking_uri = f"file://{tmp_path / 'mlruns'}"
    mlflow.set_tracking_uri(tracking_uri)
    yield tracking_uri
    mlflow.set_tracking_uri("") # Reset to default

@pytest.fixture
def dummy_run_files(tmp_path):
    """
    Create dummy run.lock and log files for testing.
    """
    save_dir = tmp_path / "test_save_dir"
    save_dir.mkdir()

    run_lock_content = {
        "config": {
            "param1": "value1",
            "nested": {"key": 123},
            "save_dir": str(save_dir)
        },
        "git": {"commit": "abcdef"}
    }
    run_lock_path = save_dir / "run.lock"
    with open(run_lock_path, "w") as f:
        yaml.dump(run_lock_content, f)

    log_file_path = save_dir / "experiment.log"
    log_file_path.write_text("This is a log file content.")

    return run_lock_path, log_file_path, save_dir

def test_mlflow_log_run_basic(mlflow_tmp_uri, dummy_run_files):
    """
    Test basic functionality: logging parameters from run.lock and an artifact.
    """
    run_lock_path, log_file_path, save_dir = dummy_run_files

    @mlflow_log_run()
    def my_experiment_function(cfg):
        return "done"

    cfg = OmegaConf.create({"save_dir": str(save_dir)})
    my_experiment_function(cfg)

    # Verify MLflow run was created and data logged
    runs = mlflow.search_runs(filter_string="", run_view_type=ViewType.ACTIVE_ONLY)
    assert len(runs) == 1
    run = mlflow.get_run(runs.iloc[0].run_id)

    assert run.data.params["param1"] == "value1"
    assert run.data.params["nested.key"] == "123"

    # Verify artifact
    artifacts = mlflow.artifacts.list_artifacts(run_id=run.info.run_id)
    assert any(a.path == log_file_path.name for a in artifacts)

def test_mlflow_log_run_no_log_file(mlflow_tmp_uri, dummy_run_files):
    """
    Test logging when no log file is provided.
    """
    run_lock_path, _, save_dir = dummy_run_files

    @mlflow_log_run(log_file_path=None)
    def my_experiment_function(cfg):
        return "done"

    cfg = OmegaConf.create({"save_dir": str(save_dir)})
    my_experiment_function(cfg)

    runs = mlflow.search_runs(filter_string="", run_view_type=ViewType.ACTIVE_ONLY)
    assert len(runs) == 1
    run = mlflow.get_run(runs.iloc[0].run_id)

    assert run.data.params["param1"] == "value1"

    assert run.data.params["nested.key"] == "123"

    artifacts = mlflow.artifacts.list_artifacts(run_id=run.info.run_id)
    assert not any(a.path == "experiment.log" for a in artifacts)

def test_mlflow_log_run_no_run_lock(mlflow_tmp_uri, tmp_path):
    """
    Test logging when run.lock file does not exist.
    """
    non_existent_run_lock = tmp_path / "non_existent_run.lock"
    log_file_path = tmp_path / "experiment.log"
    log_file_path.write_text("log content")

    @mlflow_log_run(run_lock_path=non_existent_run_lock, log_file_path=log_file_path)
    def my_experiment_function(cfg):
        return "done"

    cfg = OmegaConf.create({"save_dir": str(tmp_path)})
    my_experiment_function(cfg)

    runs = mlflow.search_runs(filter_string="", run_view_type=ViewType.ACTIVE_ONLY)
    assert len(runs) == 1
    run = mlflow.get_run(runs.iloc[0].run_id)

    assert not run.data.params # No params should be logged from run.lock

    artifacts = mlflow.artifacts.list_artifacts(run_id=run.info.run_id)
    assert any(a.path == log_file_path.name for a in artifacts)

def test_mlflow_log_run_with_config_object(mlflow_tmp_uri, tmp_path):
    """
    Test logging when the function receives a config object with save_dir.
    """
    save_dir = tmp_path / "test_run"
    save_dir.mkdir()
    
    # Create config that simulates OmegaConf structured config
    cfg = OmegaConf.create({
        "save_dir": str(save_dir),
        "param1": "value1",
        "param2": 42
    })
    
    run_lock_content = {
        "config": {
            "param1": "value1", 
            "param2": 42,
            "save_dir": str(save_dir)
        }
    }
    run_lock_path = save_dir / "run.lock"
    with open(run_lock_path, "w") as f:
        yaml.dump(run_lock_content, f)

    log_file_path = save_dir / "experiment.log"
    log_file_path.write_text("Log content with config object.")

    @mlflow_log_run(run_lock_path=run_lock_path, log_file_path=log_file_path)
    def my_diag_function(cfg):
        # Test function that receives a config object
        assert cfg.save_dir == str(save_dir)
        return "diag_done"

    my_diag_function(cfg)

    runs = mlflow.search_runs(filter_string="", run_view_type=ViewType.ACTIVE_ONLY)
    assert len(runs) == 1
    run = mlflow.get_run(runs.iloc[0].run_id)

    assert run.data.params["param1"] == "value1"
    assert run.data.params["param2"] == "42"

def test_mlflow_log_run_with_save_dir_path(mlflow_tmp_uri, tmp_path):
    """
    Test logging when the function receives a save_dir path directly.
    The decorator should load the config from the save_dir.
    """
    save_dir = tmp_path / "test_run_save_dir"
    save_dir.mkdir()
    
    # Create config file in save_dir
    config_data = {
        "save_dir": str(save_dir),
        "param1": "value1", 
        "param2": 42
    }
    config_path = save_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    
    # Create run.lock file in save_dir
    run_lock_content = {
        "config": config_data
    }
    run_lock_path = save_dir / "run.lock"
    with open(run_lock_path, "w") as f:
        yaml.dump(run_lock_content, f)

    log_file_path = save_dir / "experiment.log"
    log_file_path.write_text("Log content with save_dir path.")

    @mlflow_log_run(run_lock_path=lambda cfg: Path(cfg.save_dir) / "run.lock", 
                    log_file_path=lambda cfg: Path(cfg.save_dir) / "experiment.log")
    def my_diag_function(save_dir_path):
        # Test function that receives save_dir directly
        assert save_dir_path == str(save_dir)
        return "diag_done_with_path"

    # Call with save_dir path directly
    my_diag_function(str(save_dir))

    runs = mlflow.search_runs(filter_string="", run_view_type=ViewType.ACTIVE_ONLY)
    assert len(runs) == 1
    run = mlflow.get_run(runs.iloc[0].run_id)

    # The parameters should be loaded from the config in the save_dir
    assert run.data.params["param1"] == "value1"
    assert run.data.params["param2"] == "42"

def test_mlflow_log_run_with_callable_run_lock_path(mlflow_tmp_uri, tmp_path):
    """
    Test logging when run_lock_path is a function that takes config and returns path.
    """
    save_dir = tmp_path / "test_callable"
    save_dir.mkdir()
    
    cfg = OmegaConf.create({
        "save_dir": str(save_dir),
        "param1": "value1",
        "other_param": "test"
    })
    
    run_lock_content = {
        "config": {
            "param1": "value1", 
            "other_param": "test",
            "save_dir": str(save_dir)
        }
    }
    run_lock_path = save_dir / "run.lock"
    with open(run_lock_path, "w") as f:
        yaml.dump(run_lock_content, f)

    log_file_path = save_dir / "experiment.log"
    log_file_path.write_text("Log content with callable run_lock_path.")

    # Use a lambda function to generate the run.lock path from config
    @mlflow_log_run(run_lock_path=lambda cfg: Path(cfg.save_dir) / "run.lock",
                    log_file_path=lambda cfg: Path(cfg.save_dir) / "experiment.log")
    def my_diag_function(cfg):
        return "diag_with_callable"

    my_diag_function(cfg)

    runs = mlflow.search_runs(filter_string="", run_view_type=ViewType.ACTIVE_ONLY)
    assert len(runs) == 1
    run = mlflow.get_run(runs.iloc[0].run_id)

    assert run.data.params["param1"] == "value1"
    assert run.data.params["other_param"] == "test"

def test_mlflow_log_run_resume_and_update(mlflow_tmp_uri, tmp_path):
    """
    Test re-running the logging function on the same run ID, with updated parameters and artifacts.
    """
    run_lock_path = tmp_path / "run.lock"
    log_file_path = tmp_path / "experiment.log"

    # First run: initial state
    initial_run_lock_content = {
            "config": { "save_dir": "roro", "param_a": 1, "param_b": "initial"},
    }
    with open(run_lock_path, "w") as f:
        yaml.dump(initial_run_lock_content, f)
    log_file_path.write_text("Initial log content.")

    @mlflow_log_run(run_lock_path=run_lock_path, log_file_path=log_file_path)
    def first_experiment_function(tmp_path):
        return "first_done"
    first_experiment_function(tmp_path)

    # Get the run ID from the first run
    runs = mlflow.search_runs(filter_string="", run_view_type=ViewType.ACTIVE_ONLY)
    print(runs)
    assert len(runs) == 1
    first_run_id = runs.iloc[0].run_id

    # Assertions for the first run
    first_run = mlflow.get_run(first_run_id)
    assert first_run.data.params["param_a"] == "1"
    assert first_run.data.params["param_b"] == "initial"
    print("Arti", mlflow.artifacts.list_artifacts(run_id=first_run_id))
    assert any(a.path == log_file_path.name for a in mlflow.artifacts.list_artifacts(run_id=first_run_id))

    # Second run: updated state, using the same run ID
    updated_run_lock_content = {
        "config": {"save_dir": "roro","param_a": 2, "param_b": "updated", "param_c": True},
    }
    with open(run_lock_path, "w") as f:
        yaml.dump(updated_run_lock_content, f)
    log_file_path.write_text("Updated log content.") # Content change for artifact

    # re-running logging
    first_experiment_function(tmp_path)

    # Verify that only one run exists and it has been updated
    runs_after_second = mlflow.search_runs(filter_string="", run_view_type=ViewType.ACTIVE_ONLY)
    assert len(runs_after_second) == 2
    first_run = mlflow.get_run(first_run_id) # Get the same run again
    second_run_id = runs_after_second.query(f'run_id != "{first_run_id}"').iloc[0].run_id
    second_run = mlflow.get_run(second_run_id) # Get the same run again
    print(first_run)
    print(second_run)
    print(first_run.data.tags)
    assert  first_run.data.tags['naga.run_status'] == "deprecated"
    assert  first_run.data.tags['naga.superseded_by_run_id'] == second_run_id
    # Assert updated parameters
    assert second_run.data.params["param_a"] == "2"
    assert second_run.data.params["param_b"] == "updated"
    assert second_run.data.params["param_c"] == "True"

    # Assert artifact is still there (MLflow logs artifacts by name, overwriting if content changes)
    artifacts_after_second = mlflow.artifacts.list_artifacts(run_id=first_run_id)
    assert any(a.path == log_file_path.name for a in artifacts_after_second)

def test_mlflow_log_run_logical_run_management(mlflow_tmp_uri, tmp_path):
    """
    Test the logical run management: new runs supersede old ones,
    and runs are tagged correctly with 'active', 'deprecated', and linking IDs.
    """
    run_lock_path = tmp_path / "run.lock"
    log_file_path = tmp_path / "experiment.log"
    save_dir_identifier = "/tmp/my_model_run_A"

    # --- First execution ---
    initial_run_lock_content = {
        "config": {"param_x": 10, "save_dir": save_dir_identifier},
    }
    with open(run_lock_path, "w") as f:
        yaml.dump(initial_run_lock_content, f)
    log_file_path.write_text("Log content for run 1.")

    @mlflow_log_run(run_lock_path=run_lock_path, log_file_path=log_file_path)
    def experiment_run_1(tmp_path):
        return "run1_done"
    experiment_run_1(tmp_path)

    runs_1 = mlflow.search_runs(filter_string=f"tags.`naga.logical_run_id` = '{save_dir_identifier}'")
    assert len(runs_1) == 1
    run_1 = mlflow.get_run(runs_1.iloc[0].run_id)
    assert run_1.data.tags.get("naga.run_status") == "active"
    assert run_1.data.tags.get("naga.logical_run_id") == save_dir_identifier
    assert "naga.supersedes_run_id" not in run_1.data.tags
    assert "naga.superseded_by_run_id" not in run_1.data.tags

    # --- Second execution (should supersede run_1) ---
    updated_run_lock_content = {
        "config": {"param_x": 20, "param_y": "new", "save_dir": save_dir_identifier},
    }
    with open(run_lock_path, "w") as f:
        yaml.dump(updated_run_lock_content, f)
    log_file_path.write_text("Log content for run 2.")

    @mlflow_log_run(run_lock_path=run_lock_path, log_file_path=log_file_path)
    def experiment_run_2(tmp_path):
        return "run2_done"
    experiment_run_2(tmp_path)

    # Verify run_2 is active and supersedes run_1
    runs_2_active = mlflow.search_runs(filter_string=f"tags.`naga.logical_run_id` = '{save_dir_identifier}' AND tags.`naga.run_status` = 'active'")
    assert len(runs_2_active) == 1
    run_2 = mlflow.get_run(runs_2_active.iloc[0].run_id)
    assert run_2.data.tags.get("naga.run_status") == "active"
    assert run_2.data.tags.get("naga.logical_run_id") == save_dir_identifier
    assert run_2.data.tags.get("naga.supersedes_run_id") == run_1.info.run_id
    assert "naga.superseded_by_run_id" not in run_2.data.tags
    assert run_2.data.params["param_x"] == "20"
    assert run_2.data.params["param_y"] == "new"

    # Verify run_1 is now deprecated and superseded by run_2
    run_1_reloaded = mlflow.get_run(run_1.info.run_id)
    assert run_1_reloaded.data.tags.get("naga.run_status") == "deprecated"
    assert run_1_reloaded.data.tags.get("naga.superseded_by_run_id") == run_2.info.run_id
    assert "naga.supersedes_run_id" not in run_1_reloaded.data.tags

    # --- Third execution (should supersede run_2) ---
    final_run_lock_content = {
        "config": {"param_x": 30, "param_z": False, "save_dir": save_dir_identifier},
    }
    with open(run_lock_path, "w") as f:
        yaml.dump(final_run_lock_content, f)
    log_file_path.write_text("Log content for run 3.")

    @mlflow_log_run(run_lock_path=run_lock_path, log_file_path=log_file_path)
    def experiment_run_3(tmp_path):
        return "run3_done"
    experiment_run_3(tmp_path)

    # Verify run_3 is active and supersedes run_2
    runs_3_active = mlflow.search_runs(filter_string=f"tags.`naga.logical_run_id` = '{save_dir_identifier}' AND tags.`naga.run_status` = 'active'")
    assert len(runs_3_active) == 1
    run_3 = mlflow.get_run(runs_3_active.iloc[0].run_id)
    assert run_3.data.tags.get("naga.run_status") == "active"
    assert run_3.data.tags.get("naga.logical_run_id") == save_dir_identifier
    assert run_3.data.tags.get("naga.supersedes_run_id") == run_2.info.run_id
    assert run_3.data.params["param_x"] == "30"
    assert run_3.data.params["param_z"] == "False"

    # Verify run_2 is now deprecated and superseded by run_3
    run_2_reloaded = mlflow.get_run(run_2.info.run_id)
    assert run_2_reloaded.data.tags.get("naga.run_status") == "deprecated"
    assert run_2_reloaded.data.tags.get("naga.superseded_by_run_id") == run_3.info.run_id

def test_mlflow_log_run_logical_run_management_different_save_dir(mlflow_tmp_uri, tmp_path):
    """
    Test that a new run is created when the save_dir is different, even if the logical_run_identifier is the same.
    """

    save_dir_b = tmp_path / "runB"
    logical_run_identifier = str(save_dir_b)
    save_dir_b.mkdir()
    # --- First execution ---
    initial_run_lock_content = {
        "config": {"param_x": 10, "save_dir": str(save_dir_b)},
    }
    with open(save_dir_b / 'run.lock', "w") as f:
        yaml.dump(initial_run_lock_content, f)
    (save_dir_b / 'experiment.log').write_text("Log content for run 1.")

    @mlflow_log_run()
    def experiment_run_1(tmp_path):
        return "run1_done"
    experiment_run_1(str(save_dir_b))

    runs_1 = mlflow.search_runs(filter_string=f"tags.`naga.logical_run_id` = '{logical_run_identifier}'")
    assert len(runs_1) == 1
    run_1 = mlflow.get_run(runs_1.iloc[0].run_id)
    assert run_1.data.tags.get("naga.run_status") == "active"
    assert run_1.data.tags.get("naga.logical_run_id") == logical_run_identifier

    save_dir_c = tmp_path / "runC"
    save_dir_c.mkdir()
    # --- Second execution (with a different save_dir) ---
    updated_run_lock_content = {
        "config": {"param_x": 20, "save_dir": str(save_dir_c)}
    }
    with open(save_dir_c / 'run.lock', "w") as f:
        yaml.dump(updated_run_lock_content, f)
    (save_dir_c / 'experiment.log').write_text("Log content for run 2.")

    @mlflow_log_run()
    def experiment_run_2(save_dir):
        return "run2_done"
    experiment_run_2(tmp_path)

    # Verify that a new run was created and the first run was not deprecated
    runs_2 = mlflow.search_runs(filter_string=f"tags.`naga.logical_run_id` = '{logical_run_identifier}'")
    assert len(runs_2) == 1 # The second run should not have the same logical run id
    run_1_reloaded = mlflow.get_run(run_1.info.run_id)
    assert run_1_reloaded.data.tags.get("naga.run_status") == "active"


def test_mlflow_log_run_no_save_dir_in_config(mlflow_tmp_uri, tmp_path):
    """
    Test logging when run.lock exists but 'save_dir' is missing from config.
    Should not perform logical run management, but still log parameters.
    """
    run_lock_path = tmp_path / "run_no_save_dir.lock"
    log_file_path = tmp_path / "experiment_no_save_dir.log"

    run_lock_content = {
        "config": {"param_only": "value_only"},
        "git": {"commit": "deadbeef"}
    }
    with open(run_lock_path, "w") as f:
        yaml.dump(run_lock_content, f)
    log_file_path.write_text("Log content without save_dir.")

    @mlflow_log_run(run_lock_path=run_lock_path, log_file_path=log_file_path)
    def my_experiment_function_no_save_dir(tmp_path):
        return "done_no_save_dir"

    my_experiment_function_no_save_dir(tmp_path)

    runs = mlflow.search_runs(filter_string="", run_view_type=ViewType.ACTIVE_ONLY)
    assert len(runs) == 1
    run = mlflow.get_run(runs.iloc[0].run_id)

    assert run.data.params["param_only"] == "value_only"
    assert "naga.logical_run_id" not in run.data.tags
    assert "naga.run_status" not in run.data.tags
    assert any(a.path == log_file_path.name for a in mlflow.artifacts.list_artifacts(run_id=run.info.run_id))
