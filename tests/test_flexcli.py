import pytest
from omegaconf import OmegaConf
from dataclasses import dataclass
import sys
from unittest.mock import patch, MagicMock

from pathlib import Path
from flexlock.flexcli import flexcli


# Define a dataclass for the configuration schema
@dataclass
class MyConfig:
    param: int = 1
    nested: str = "default"
    save_dir: str = "/tmp/flexlock_tests"


# Create a decorated function to be used in tests
@flexcli(default_config=MyConfig)
def main(cfg):
    # In a real scenario, this function would be the entry point of the script.
    # For testing, we often just return the config to inspect it.
    return cfg


@pytest.fixture
def config_file(tmp_path):
    """Create a temporary base config file."""
    base_path = tmp_path / "base.yaml"
    base_path.write_text(f"param: 10\nnested: 'from_file'\nsave_dir: {tmp_path}")
    return base_path


def test_flexcli_default_config():
    """Test that the default config from the dataclass is used."""
    cfg = main()
    assert cfg.param == 1
    assert cfg.nested == "default"


def test_flexcli_cli_mode_with_config_file(config_file):
    """Test loading a config from a file via CLI arguments."""
    with patch.object(sys, "argv", ["script.py", "--config", str(config_file)]):
        cfg = main()
        assert cfg.param == 10
        assert cfg.nested == "from_file"


def test_flexcli_cli_mode_with_overrides(config_file):
    """Test overriding config values from the CLI."""
    with patch.object(
        sys,
        "argv",
        [
            "script.py",
            "--config",
            str(config_file),
            "-o",
            "param=20",
            "nested=cli_override",
        ],
    ):
        cfg = main()
        assert cfg.param == 20
        assert cfg.nested == "cli_override"


def test_flexcli_programmatic_mode():
    """Test calling the decorated function programmatically with kwargs."""
    cfg = main(param=30, nested="programmatic_override")
    assert cfg.param == 30
    assert cfg.nested == "programmatic_override"


@patch("flexlock.flexcli.ParallelExecutor")
def test_flexcli_parallel_execution_is_triggered(mock_executor, config_file, tmp_path):
    """
    Verify that when task-related arguments are provided, the ParallelExecutor
    is instantiated and its `run` method is called.
    """
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text("- task1\n- task2")

    slurm_config_file = tmp_path / "slurm.yaml"
    slurm_config_file.write_text("partition: 'compute'")

    with patch.object(
        sys,
        "argv",
        [
            "script.py",
            "--config",
            str(config_file),
            "--tasks",
            str(tasks_file),
            "--task-to",
            "experiment.name",
            "--n_jobs",
            "4",
            "--slurm_config",
            str(slurm_config_file),
        ],
    ):
        main(cfg=OmegaConf.create({"save_dir": str(tmp_path)}))

    # Check that the executor was called with the correct arguments
    mock_executor.assert_called_once()

    # Inspect the keyword arguments passed to the ParallelExecutor constructor
    _, kwargs = mock_executor.call_args
    assert kwargs["tasks"] == ["task1", "task2"]
    assert kwargs["task_to"] == "experiment.name"
    assert kwargs["n_jobs"] == 4
    assert kwargs["slurm_config"] == str(slurm_config_file)
    assert kwargs["pbs_config"] is None  # Ensure pbs_config was not set

    # Check that the run method was called on the instance
    executor_instance = mock_executor.return_value
    executor_instance.run.assert_called_once()


@patch("flexlock.flexcli.ParallelExecutor")
def test_flexcli_uses_pbs_config(mock_executor, config_file, tmp_path):
    """Verify that the --pbs_config argument is correctly passed to the executor."""
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text("- task1")

    pbs_config_file = tmp_path / "pbs.yaml"
    pbs_config_file.write_text("queue: 'work'")

    with patch.object(
        sys,
        "argv",
        [
            "script.py",
            "--config",
            str(config_file),
            "--tasks",
            str(tasks_file),
            "--task-to",
            "experiment.name",
            "--pbs_config",
            str(pbs_config_file),
        ],
    ):
        main(cfg=OmegaConf.create({"save_dir": str(tmp_path)}))

    _, kwargs = mock_executor.call_args
    assert kwargs["pbs_config"] == str(pbs_config_file)
    assert kwargs["slurm_config"] is None
