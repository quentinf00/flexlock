"""
Tests for multistage config handling with interpolation.
This tests the specific case mentioned in TODO.md where nested config
interpolation should work properly when passed to functions.
"""

import tempfile
from pathlib import Path
from omegaconf import OmegaConf
from dataclasses import dataclass
from flexlock.flexcli import flexcli
from flexlock.parallel import load_tasks
import pytest


def test_nested_config_interpolation_simple_run():
    """Test that nested config interpolation works in a simple run."""

    @dataclass
    class Cfg:
        p: int = 1

    def myfn(cfg: Cfg):
        # Access the interpolated value
        return cfg.p

    # Create a YAML config with interpolation
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
param: 5
cfg:
    p: ${param}
""")
        config_path = f.name

    try:
        # Load the global config
        glob_cfg = OmegaConf.load(config_path)

        # The cfg.p should be resolved to 5 when accessed, but it might not work if
        # interpolation context is lost when passing glob_cfg.cfg
        assert OmegaConf.select(glob_cfg, "cfg.p") == 5  # Still contains reference

        # This should resolve to the value of 'param' which is 5
        resolved_cfg = OmegaConf.to_container(glob_cfg, resolve=True)
        expected_value = resolved_cfg["cfg"]["p"]
        assert expected_value == 5, f"Expected 5, got {expected_value}"

        # Now test the actual function call - this is the key issue
        result = myfn(glob_cfg.cfg)
        assert result == 5, f"Function should receive resolved value 5, got {result}"

    finally:
        Path(config_path).unlink()


def test_nested_config_interpolation_with_experiment_selection():
    """Test config with --experiment selection and interpolation."""

    @dataclass
    class Config:
        p: int = 1

    @flexcli(default_config=Config)
    def main(cfg: Config):
        return cfg

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
param: 10
experiments:
  exp1:
    p: ${param}
""")
        config_path = f.name

    import sys
    from unittest.mock import patch

    try:
        with patch.object(
            sys,
            "argv",
            ["script.py", "--config", config_path, "--experiment", "experiments.exp1"],
        ):
            cfg = main()
            # cfg.p should resolve to 10 from ${param}
            assert cfg.p == 10, f"Expected cfg.p to resolve to 10, got {cfg.p}"

    finally:
        Path(config_path).unlink()


def test_nested_config_interpolation_multitask_run():
    """Test nested config interpolation works in multitask runs."""

    @dataclass
    class Config:
        p: int = 1
        some_param: str = "???"
        save_dir: str = "/tmp/test_multitask"

    results = []

    @flexcli(default_config=Config)
    def main(cfg: Config):
        results.append(cfg.p)
        return cfg.p

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
param: 20
cfg:
    p: ${param}
    some_param: 1
    save_dir: /tmp/test_multitask
""")
        config_path = f.name

    # Create a tasks file
    tasks_file = Path(config_path).with_name("tasks.txt")
    tasks_file.write_text("1\n2")

    import sys
    from unittest.mock import patch

    try:
        # Test that this doesn't work as expected currently - the nested cfg.p
        # may not resolve to 20 due to loss of interpolation context
        with patch.object(
            sys,
            "argv",
            [
                "script.py",
                "--config",
                config_path,
                "--experiment",
                "cfg",
                "--tasks",
                str(tasks_file),
                "--task-to",
                "some_param",  # Not merging into root to avoid conflicts
            ],
        ):
            main()

        # We're mainly testing that the config loading doesn't fail
        # The results list should have values for each task processed
        # For now, just ensure no exception is raised during config processing

    finally:
        Path(config_path).unlink()
        if tasks_file.exists():
            tasks_file.unlink()


def test_multitask_with_experiment_and_interpolation():
    """Test the specific multitask scenario with experiment selection and interpolation."""

    @dataclass
    class Config:
        p: int = 1
        save_dir: str = "/tmp/test_exp_multitask"

    task_results = []

    @flexcli(default_config=Config)
    def main(cfg: Config):
        task_results.append(cfg.p)
        return cfg.p

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
param: 30
experiments:
  exp1:
    p: ${param}
    save_dir: /tmp/test_exp_multitask
""")
        config_path = f.name

    # Create a tasks file
    tasks_file = Path(config_path).with_name("tasks2.txt")
    tasks_file.write_text("task1\ntask2")

    import sys
    from unittest.mock import patch

    try:
        # This should work once we fix the interpolation context issue
        with patch.object(
            sys,
            "argv",
            [
                "script.py",
                "--config",
                config_path,
                "--experiment",
                "experiments.exp1",
                "--tasks",
                str(tasks_file),
                "--task-to",
                "task_id",  # Add task-specific field
                "--n_jobs",
                "1",
            ],
        ):
            main()

        # Each task should have processed successfully
        # The cfg.p should have resolved to 30 from ${param}
        # This will only work correctly once the fix is implemented

    finally:
        Path(config_path).unlink()
        if tasks_file.exists():
            tasks_file.unlink()


def test_interpolation_context_preservation():
    """Test that interpolation context is preserved when extracting nested configs."""

    yaml_content = """
param: 42
cfg:
    p: ${param}
    nested:
        value: ${param}
other_param: 99
"""

    cfg = OmegaConf.create(yaml_content)

    # Access nested config directly - this should still have interpolation context
    nested_cfg = cfg.cfg

    # The nested config should still be able to resolve interpolations
    # However, if the resolution context is lost, this won't work
    assert OmegaConf.is_missing(nested_cfg, "p") == False  # Should be resolvable

    # Get the resolved value
    resolved = OmegaConf.to_container(nested_cfg, resolve=True)
    assert resolved["p"] == 42
    assert resolved["nested"]["value"] == 42


if __name__ == "__main__":
    test_nested_config_interpolation_simple_run()
    test_nested_config_interpolation_with_experiment_selection()
    test_interpolation_context_preservation()
    print("All tests passed!")
