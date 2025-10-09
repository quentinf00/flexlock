import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import yaml
import mlflow
import pandas as pd

from flexlock.mlflowlink import mlflowlink

@pytest.fixture
def mock_mlflow():
    """Fixture to mock all necessary mlflow functions."""
    with patch('flexlock.mlflowlink.mlflow') as mock_mlflow_module:
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

def test_mlflowlink_starts_run_and_sets_tags(mock_mlflow, dummy_run_files):
    """Test that the context manager starts a run and sets the correct initial tags."""
    save_dir = dummy_run_files
    
    with mlflowlink(path=str(save_dir)):
        # We are testing what happens upon entering the context
        pass

    # start_run is called for the new run and again to deprecate the old one
    assert mock_mlflow.start_run.call_count == 2
    
    # Check that initial tags are set correctly on the new run
    mock_mlflow.set_tag.assert_any_call("flexlock.logical_run_id", str(save_dir.as_posix()))
    mock_mlflow.set_tag.assert_any_call("flexlock.run_status", "active")
    mock_mlflow.set_tag.assert_any_call("flexlock.supersedes_run_id", "previous_run_id")

def test_mlflowlink_logs_artifacts_and_params(mock_mlflow, dummy_run_files):
    """Test that artifacts and parameters are logged on exit."""
    save_dir = dummy_run_files
    
    with mlflowlink(path=str(save_dir)):
        pass # Logic happens on exit

    # Check that params are logged
    expected_params = {"config.param1": "value1", "config.nested.key": 123, "config.save_dir": str(save_dir)}
    mock_mlflow.log_params.assert_called_once_with(expected_params, run_id='test_run_id')

    # Check that artifacts are logged
    mock_mlflow.log_artifact.assert_any_call(str(save_dir / "run.lock"), run_id='test_run_id')
    mock_mlflow.log_artifact.assert_any_call(str(save_dir / "experiment.log"), run_id='test_run_id')

def test_mlflowlink_deprecates_previous_run(mock_mlflow, dummy_run_files):
    """Test that the previous active run is deprecated on exit."""
    save_dir = dummy_run_files
    
    with mlflowlink(path=str(save_dir)):
        pass # Deprecation logic happens after the block

    # A second call to start_run happens to deprecate the old run
    assert mock_mlflow.start_run.call_count == 2
    mock_mlflow.start_run.assert_called_with(run_id="previous_run_id")
    
    # Check tags for deprecation
    mock_mlflow.set_tag.assert_any_call("flexlock.run_status", "deprecated")
    mock_mlflow.set_tag.assert_any_call("flexlock.superseded_by_run_id", "test_run_id")

def test_mlflowlink_no_previous_run(mock_mlflow, dummy_run_files):
    """Test behavior when no previous active run is found."""
    save_dir = dummy_run_files
    mock_mlflow.search_runs.return_value = pd.DataFrame() # Simulate no runs found

    with mlflowlink(path=str(save_dir)):
        pass

    # start_run should only be called once (for the new run)
    mock_mlflow.start_run.assert_called_once()
    
    # Ensure it doesn't try to set the 'supersedes' tag
    for call in mock_mlflow.set_tag.call_args_list:
        assert call.args[0] != "flexlock.supersedes_run_id"

def test_mlflowlink_no_snapshot_file(mock_mlflow, tmp_path):
    """Test that it runs without error if run.lock is missing."""
    save_dir = tmp_path / "empty_dir"
    save_dir.mkdir()
    (save_dir / "experiment.log").write_text("log only")

    with mlflowlink(path=str(save_dir)):
        pass

    mock_mlflow.log_params.assert_not_called()
    mock_mlflow.log_artifact.assert_called_once_with(str(save_dir / "experiment.log"), run_id="test_run_id")
