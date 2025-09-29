import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import yaml
import mlflow
import pandas as pd

from naga.mlflow_log import mlflow_lock

@pytest.fixture
def mock_mlflow():
    """Fixture to mock all necessary mlflow functions."""
    with patch('naga.mlflow_log.mlflow') as mock_mlflow_module:
        # Mock the run object that `start_run` returns
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        
        # Mock the context manager part of start_run
        mock_mlflow_module.start_run.return_value.__enter__.return_value = mock_run
        
        # Mock search_runs to return a DataFrame
        mock_df = pd.DataFrame({"run_id": ["previous_run_id"]})
        mock_mlflow_module.search_runs.return_value = mock_df
        
        yield mock_mlflow_module

@pytest.fixture
def dummy_run_files(tmp_path):
    """Create dummy run.lock and log files for testing."""
    save_dir = tmp_path / "test_save_dir"
    save_dir.mkdir()

    run_lock_content = {
        "config": {
            "param1": "value1",
            "nested": {"key": 123},
            "save_dir": str(save_dir)
        }
    }
    (save_dir / "run.lock").write_text(yaml.dump(run_lock_content))
    (save_dir / "experiment.log").write_text("This is a log.")
    
    return save_dir

def test_mlflow_lock_starts_run_and_sets_tags(mock_mlflow, dummy_run_files):
    """Test that the context manager starts a run and sets the correct initial tags."""
    save_dir = dummy_run_files
    
    with mlflow_lock(path=str(save_dir)):
        # We are testing what happens upon entering the context
        pass

    # start_run is called for the new run and again to deprecate the old one
    assert mock_mlflow.start_run.call_count == 2
    
    # Check that initial tags are set correctly on the new run
    mock_mlflow.set_tag.assert_any_call("naga.logical_run_id", str(save_dir.as_posix()))
    mock_mlflow.set_tag.assert_any_call("naga.run_status", "active")
    mock_mlflow.set_tag.assert_any_call("naga.supersedes_run_id", "previous_run_id")

def test_mlflow_lock_logs_artifacts_and_params(mock_mlflow, dummy_run_files):
    """Test that artifacts and parameters are logged on exit."""
    save_dir = dummy_run_files
    
    with mlflow_lock(path=str(save_dir)):
        pass # Logic happens on exit

    # Check that params are logged
    expected_params = {"param1": "value1", "nested.key": 123, "save_dir": str(save_dir)}
    mock_mlflow.log_params.assert_called_once_with(expected_params)

    # Check that artifacts are logged
    mock_mlflow.log_artifact.assert_any_call(str(save_dir / "run.lock"))
    mock_mlflow.log_artifact.assert_any_call(str(save_dir / "experiment.log"))

def test_mlflow_lock_deprecates_previous_run(mock_mlflow, dummy_run_files):
    """Test that the previous active run is deprecated on exit."""
    save_dir = dummy_run_files
    
    with mlflow_lock(path=str(save_dir)):
        pass # Deprecation logic happens after the block

    # A second call to start_run happens to deprecate the old run
    assert mock_mlflow.start_run.call_count == 2
    mock_mlflow.start_run.assert_called_with(run_id="previous_run_id")
    
    # Check tags for deprecation
    mock_mlflow.set_tag.assert_any_call("naga.run_status", "deprecated")
    mock_mlflow.set_tag.assert_any_call("naga.superseded_by_run_id", "test_run_id")

def test_mlflow_lock_no_previous_run(mock_mlflow, dummy_run_files):
    """Test behavior when no previous active run is found."""
    save_dir = dummy_run_files
    mock_mlflow.search_runs.return_value = pd.DataFrame() # Simulate no runs found

    with mlflow_lock(path=str(save_dir)):
        pass

    # start_run should only be called once (for the new run)
    mock_mlflow.start_run.assert_called_once()
    
    # Ensure it doesn't try to set the 'supersedes' tag
    for call in mock_mlflow.set_tag.call_args_list:
        assert call.args[0] != "naga.supersedes_run_id"

def test_mlflow_lock_no_runlock_file(mock_mlflow, tmp_path):
    """Test that it runs without error if run.lock is missing."""
    save_dir = tmp_path / "empty_dir"
    save_dir.mkdir()
    (save_dir / "experiment.log").write_text("log only")

    with mlflow_lock(path=str(save_dir)):
        pass

    mock_mlflow.log_params.assert_not_called()
    mock_mlflow.log_artifact.assert_called_once_with(str(save_dir / "experiment.log"))
