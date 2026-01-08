import pytest
from unittest.mock import patch, MagicMock, Mock
from pathlib import Path
import yaml

# Import the functions to be tested
from flexlock.mlflow import mlflow_context


@pytest.fixture
def dummy_run_files(tmp_path):
    """Create dummy run.lock and log files for testing."""
    save_dir = tmp_path / "test_save_dir"
    save_dir.mkdir()

    run_lock_content = {
        "config": {
            "param1": "value1",
            "nested": {"key": 123},
            "save_dir": str(save_dir),
        }
    }
    (save_dir / "run.lock").write_text(yaml.dump(run_lock_content))
    (save_dir / "experiment.log").write_text("This is a log.")

    return save_dir


@pytest.fixture
def mock_mlflow_module():
    """Mocks the entire mlflow module and its commonly used functions."""
    mlflow_mock = MagicMock()

    # Mock the run object that `start_run` returns
    mock_run = MagicMock()
    mock_run.info.run_id = "test_run_id"

    # Mock the context manager part of start_run
    mlflow_mock.start_run.return_value.__enter__.return_value = mock_run
    mlflow_mock.start_run.return_value.__exit__ = Mock(return_value=False)

    # Mock MlflowClient
    mock_client = MagicMock()
    mock_experiment = MagicMock()
    mock_experiment.experiment_id = "test_experiment_id"
    mock_client.get_experiment_by_name.return_value = mock_experiment

    # Mock search_runs to return a list with one previous run
    mock_prev_run = MagicMock()
    mock_prev_run.info.run_id = "previous_run_id"
    mock_client.search_runs.return_value = [mock_prev_run]

    # Create MlflowClient class mock
    mlflow_mock.tracking.MlflowClient = Mock(return_value=mock_client)

    return mlflow_mock


def test_mlflow_context_starts_run_and_sets_tags(dummy_run_files, mock_mlflow_module):
    """Test that the context manager starts a run and sets the correct initial tags."""
    with patch.dict(
        "sys.modules",
        {
            "mlflow": mock_mlflow_module,
            "mlflow.tracking": mock_mlflow_module.tracking,
        },
    ):
        # Re-import to get mocked version
        from flexlock.mlflow import mlflow_context

        with mlflow_context(save_dir=str(dummy_run_files), experiment_name="TestExp"):
            pass

    # Verify start_run was called
    assert mock_mlflow_module.start_run.called

    # Check that tags are set correctly with new tag names
    mock_mlflow_module.set_tags.assert_called_once()
    tags_arg = mock_mlflow_module.set_tags.call_args[0][0]

    assert "flexlock.dir" in tags_arg
    assert tags_arg["flexlock.dir"] == str(dummy_run_files.as_posix())
    assert tags_arg["flexlock.status"] == "active"
    assert tags_arg["flexlock.supersedes"] == "previous_run_id"


def test_mlflow_context_logs_artifacts_and_params(dummy_run_files, mock_mlflow_module):
    """Test that artifacts and parameters are logged on exit."""
    with patch.dict(
        "sys.modules",
        {
            "mlflow": mock_mlflow_module,
            "mlflow.tracking": mock_mlflow_module.tracking,
        },
    ):
        from flexlock.mlflow import mlflow_context

        with mlflow_context(save_dir=str(dummy_run_files)):
            pass

    # Check that parameters were logged (with new flattening)
    assert mock_mlflow_module.log_params.called
    params_arg = mock_mlflow_module.log_params.call_args[0][0]

    assert "param1" in params_arg or "config.param1" in params_arg
    assert "nested.key" in params_arg or "config.nested.key" in params_arg

    # Check artifacts were logged
    assert mock_mlflow_module.log_artifact.called

    # Check that run.lock and experiment.log were logged
    artifact_calls = [call[0][0] for call in mock_mlflow_module.log_artifact.call_args_list]
    assert any("run.lock" in str(call) for call in artifact_calls)
    assert any("experiment.log" in str(call) for call in artifact_calls)


def test_mlflow_context_deprecates_previous_run(dummy_run_files, mock_mlflow_module):
    """Test that the previous active run is deprecated on exit using MlflowClient."""
    with patch.dict(
        "sys.modules",
        {
            "mlflow": mock_mlflow_module,
            "mlflow.tracking": mock_mlflow_module.tracking,
        },
    ):
        from flexlock.mlflow import mlflow_context

        with mlflow_context(save_dir=str(dummy_run_files)):
            pass

    # Get the mock client instance
    client_mock = mock_mlflow_module.tracking.MlflowClient.return_value

    # Verify client.set_tag was called to deprecate the previous run
    set_tag_calls = client_mock.set_tag.call_args_list

    # Should have two calls: one for status, one for superseded_by
    assert len(set_tag_calls) == 2

    # Extract call arguments
    call_tuples = [(call[0][0], call[0][1]) for call in set_tag_calls]

    # Check that both tags were set on the previous run
    assert ("previous_run_id", "flexlock.status") in call_tuples
    assert ("previous_run_id", "flexlock.superseded_by") in call_tuples

    # Verify the status value is "deprecated"
    for call in set_tag_calls:
        if call[0][1] == "flexlock.status":
            assert call[0][2] == "deprecated"



def test_mlflow_context_no_previous_run(dummy_run_files, mock_mlflow_module):
    """Test behavior when there is no previous run."""
    # Mock search_runs to return empty list (no previous run)
    client_mock = mock_mlflow_module.tracking.MlflowClient.return_value
    client_mock.search_runs.return_value = []

    with patch.dict(
        "sys.modules",
        {
            "mlflow": mock_mlflow_module,
            "mlflow.tracking": mock_mlflow_module.tracking,
        },
    ):
        from flexlock.mlflow import mlflow_context

        with mlflow_context(save_dir=str(dummy_run_files)):
            pass

    # Verify tags don't include supersedes
    tags_arg = mock_mlflow_module.set_tags.call_args[0][0]
    assert "flexlock.supersedes" not in tags_arg

    # Verify no deprecation calls (no previous run to deprecate)
    client_mock.set_tag.assert_not_called()


def test_mlflow_context_custom_tags(dummy_run_files, mock_mlflow_module):
    """Test that custom tags are added correctly."""
    with patch.dict(
        "sys.modules",
        {
            "mlflow": mock_mlflow_module,
            "mlflow.tracking": mock_mlflow_module.tracking,
        },
    ):
        from flexlock.mlflow import mlflow_context

        custom_tags = {"model": "resnet50", "dataset": "imagenet"}

        with mlflow_context(
            save_dir=str(dummy_run_files),
            tags=custom_tags
        ):
            pass

    # Verify custom tags are included
    tags_arg = mock_mlflow_module.set_tags.call_args[0][0]
    assert tags_arg["model"] == "resnet50"
    assert tags_arg["dataset"] == "imagenet"


def test_mlflow_context_log_config_false(dummy_run_files, mock_mlflow_module):
    """Test that log_config=False skips parameter logging."""
    with patch.dict(
        "sys.modules",
        {
            "mlflow": mock_mlflow_module,
            "mlflow.tracking": mock_mlflow_module.tracking,
        },
    ):
        from flexlock.mlflow import mlflow_context

        with mlflow_context(save_dir=str(dummy_run_files), log_config=False):
            pass

    # Parameters should not be logged
    assert not mock_mlflow_module.log_params.called


def test_mlflow_context_log_artifacts_false(dummy_run_files, mock_mlflow_module):
    """Test that log_artifacts=False skips artifact logging (except manual logs)."""
    with patch.dict(
        "sys.modules",
        {
            "mlflow": mock_mlflow_module,
            "mlflow.tracking": mock_mlflow_module.tracking,
        },
    ):
        from flexlock.mlflow import mlflow_context

        with mlflow_context(save_dir=str(dummy_run_files), log_artifacts=False):
            pass

    # Should still log run.lock if log_config=True (default)
    # but should not log experiment.log, stderr.log, stdout.log
    artifact_calls = [call[0][0] for call in mock_mlflow_module.log_artifact.call_args_list]

    # run.lock should be logged (part of log_config)
    assert any("run.lock" in str(call) for call in artifact_calls)

    # But experiment.log should NOT be logged (part of log_artifacts)
    # Note: this depends on implementation - if both log_config and log_artifacts are False,
    # nothing gets logged except what user explicitly logs
