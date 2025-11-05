import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import yaml
import pandas as pd

# Import the function to be tested
from flexlock.mlflowlink import mlflowlink

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

# A fixture to provide a mocked mlflow module
@pytest.fixture
def mock_mlflow_module():
    """Mocks the entire mlflow module and its commonly used functions."""
    mlflow_mock = MagicMock()
    
    # Mock the run object that `start_run` returns
    mock_run = MagicMock()
    mock_run.info.run_id = "test_run_id"
    
    # Mock the context manager part of start_run
    mlflow_mock.start_run.return_value.__enter__.return_value = mock_run
    
    # Mock search_runs to return a DataFrame
    mock_df = pd.DataFrame({"run_id": ["previous_run_id"]})
    mlflow_mock.search_runs.return_value = mock_df
    
    return mlflow_mock

def test_mlflowlink_starts_run_and_sets_tags(dummy_run_files, mock_mlflow_module):
    """Test that the context manager starts a run and sets the correct initial tags."""
    with patch.dict('sys.modules', {'mlflow': mock_mlflow_module,}):
        with mlflowlink(path=str(dummy_run_files)):
            pass

    # start_run is called for the new run and again to deprecate the old one
    assert mock_mlflow_module.start_run.call_count == 2
    
    # Check that initial tags are set correctly on the new run
    mock_mlflow_module.set_tag.assert_any_call("flexlock.logical_run_id", str(dummy_run_files.as_posix()))
    mock_mlflow_module.set_tag.assert_any_call("flexlock.run_status", "active")
    mock_mlflow_module.set_tag.assert_any_call("flexlock.supersedes_run_id", "previous_run_id")

def test_mlflowlink_logs_artifacts_and_params(dummy_run_files, mock_mlflow_module):
    """Test that artifacts and parameters are logged on exit."""
    with patch.dict('sys.modules', {'mlflow': mock_mlflow_module, }):
        with mlflowlink(path=str(dummy_run_files)):
            pass

    expected_params = {"config.param1": "value1", "config.nested.key": 123, "config.save_dir": str(dummy_run_files)}
    mock_mlflow_module.log_params.assert_called_once_with(expected_params, run_id='test_run_id')
    mock_mlflow_module.log_artifact.assert_any_call(str(dummy_run_files / "run.lock"), run_id='test_run_id')
    mock_mlflow_module.log_artifact.assert_any_call(str(dummy_run_files / "experiment.log"), run_id='test_run_id')

def test_mlflowlink_deprecates_previous_run(dummy_run_files, mock_mlflow_module):
    """Test that the previous active run is deprecated on exit."""
    with patch.dict('sys.modules', {'mlflow': mock_mlflow_module, 'pandas': MagicMock()}):
        with mlflowlink(path=str(dummy_run_files)):
            pass

    assert mock_mlflow_module.start_run.call_count == 2
    mock_mlflow_module.start_run.assert_called_with(run_id="previous_run_id")
    mock_mlflow_module.set_tag.assert_any_call("flexlock.run_status", "deprecated")
    mock_mlflow_module.set_tag.assert_any_call("flexlock.superseded_by_run_id", "test_run_id")
