import pytest
from pathlib import Path
import tempfile
from omegaconf import OmegaConf
from flexlock.runner import FlexLockRunner


def test_flexlockrunner_initialization():
    """Test that FlexLockRunner initializes with correct arguments."""
    runner = FlexLockRunner()
    assert runner.parser is not None
    
    # Check that required arguments are defined
    # We'll test parsing with minimal required args
    args = ['--defaults', 'test.defaults']
    parsed = runner.parser.parse_args(args)
    assert parsed.defaults == 'test.defaults'


def test_flexlockrunner_load_config_with_defaults():
    """Test loading config with defaults."""
    runner = FlexLockRunner()

    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('defaults = {"param1": 1, "nested": {"value": 10}}\n')
        temp_file = f.name

    try:
        args = ['--defaults', f'{temp_file}:defaults']
        parsed = runner.parser.parse_args(args)
        config = runner.load_config(parsed)

        assert 'param1' in config
        assert config['param1'] == 1
        assert 'nested' in config
        assert config['nested']['value'] == 10
    finally:
        Path(temp_file).unlink()




def test_help_flag_prints_help_and_does_not_execute(tmp_path, capsys):
    """`flexlock-run --help` must print help and return without running.

    Pre-fix the flag was parsed (action='store_true') but never honoured —
    the runner went on to submit the configured task, running the user's
    function instead of showing help.
    """
    import sys
    from unittest.mock import patch

    runner = FlexLockRunner()

    # Build a minimal valid argv so any downstream code path would have
    # something to execute if --help wasn't honoured.
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text("lr: 0.01\nsave_dir: " + str(tmp_path / "out") + "\n")

    with patch("flexlock.api.Project.submit") as mock_submit:
        out = runner.run(["--help", "-c", str(cfg_file)])

    assert out is None
    mock_submit.assert_not_called()
    captured = capsys.readouterr().out
    assert "usage:" in captured.lower() or "--defaults" in captured


def test_flexlockrunner_prepare_node_injects_save_dir():
    """Test that _prepare_node injects save_dir if missing."""
    runner = FlexLockRunner()
    
    cfg = OmegaConf.create({"param": 1})
    prepared_cfg = runner._prepare_node(cfg, name="test_exp")
    
    assert "save_dir" in prepared_cfg
    assert "outputs/test_exp" in prepared_cfg.save_dir


def test_flexlockrunner_prepare_node_preserves_existing_save_dir():
    """Test that _prepare_node preserves existing save_dir."""
    runner = FlexLockRunner()
    
    cfg = OmegaConf.create({"param": 1, "save_dir": "/existing/path"})
    prepared_cfg = runner._prepare_node(cfg, name="test_exp")
    
    assert prepared_cfg.save_dir == "/existing/path"


def test_flexlockrunner_load_config_with_config_file(tmp_path):
    """Test loading config with base YAML file."""
    runner = FlexLockRunner()
    
    # Create a temporary config file
    config_file = tmp_path / "config.yaml"
    config_file.write_text("param1: 5\nnested:\n  value: 20\n")
    
    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('defaults = {"param1": 1, "nested": {"value": 10}, "extra": "default"}\n')
        temp_file = f.name
    
    try:
        args = ['--defaults', f'{temp_file}:defaults', '--config', str(config_file)]
        parsed = runner.parser.parse_args(args)
        config = runner.load_config(parsed)
        
        assert config['param1'] == 5  # Overridden by config file
        assert config['nested']['value'] == 20  # Overridden by config file
        assert config['extra'] == 'default'  # From defaults
    finally:
        Path(temp_file).unlink()


def test_flexlockrunner_load_config_with_outer_overrides():
    """Test loading config with outer overrides."""
    runner = FlexLockRunner()
    
    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('defaults = {"param1": 1, "nested": {"value": 10}}\n')
        temp_file = f.name
    
    try:
        args = ['--defaults', f'{temp_file}:defaults', '--overrides', 'param1=100', 'nested.value=200']
        parsed = runner.parser.parse_args(args)
        config = runner.load_config(parsed)

        assert config['param1'] == 100
        assert config['nested']['value'] == 200
    finally:
        Path(temp_file).unlink()


def test_flexlockrunner_overrides_repeatable():
    """`-o` is repeatable: `-o a=1 -o b=2` merges both groups."""
    runner = FlexLockRunner()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('defaults = {"a": 0, "b": 0}\n')
        temp_file = f.name

    try:
        args = ['--defaults', f'{temp_file}:defaults', '-o', 'a=1', '-o', 'b=2']
        parsed = runner.parser.parse_args(args)
        config = runner.load_config(parsed)

        assert config['a'] == 1
        assert config['b'] == 2
    finally:
        Path(temp_file).unlink()


def test_flexlockrunner_load_config_with_selection():
    """Test loading config with node selection."""
    runner = FlexLockRunner()

    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('''
defaults =  {
    "stage1": {"param1": 1, "nested": {"value": 10}},
    "stage2": {"param2": 2, "other": {"value": 20}}
}
''')
        temp_file = f.name

    try:
        args = ['--defaults', f'{temp_file}:defaults', '--select', 'stage1']
        parsed = runner.parser.parse_args(args)
        # Instead of running the full loader, we test the selection separately
        root_cfg = runner.load_config(parsed)
        node_cfg = runner.parser.parse_args(args)  # This is how selection would work in the actual run method

        # For this test, we focus on the selection logic
        selected = OmegaConf.select(root_cfg, 'stage1')
        assert selected['param1'] == 1
        assert selected['nested']['value'] == 10
    finally:
        Path(temp_file).unlink()


# --- Test Cases for new exception handling and validation ---


def test_mutually_exclusive_sweep_args():
    """Test that providing multiple sweep sources raises FlexLockValidationError."""
    from flexlock.runner import FlexLockRunner
    from flexlock.exceptions import FlexLockValidationError
    import tempfile
    from pathlib import Path
    
    runner = FlexLockRunner()
    
    # Create a minimal config
    cfg = OmegaConf.create({'model': 'test'})
    
    # Create a temporary sweep file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write('- task1\n- task2\n')
        sweep_file = f.name
    
    try:
        # Create args with multiple sweep sources
        import argparse
        args = argparse.Namespace(
            sweep_key='experiments.sweep',
            sweep_file=sweep_file,
            sweep='1,2,3'
        )
        
        # Should raise FlexLockValidationError
        with pytest.raises(FlexLockValidationError, match="Multiple sweep sources provided"):
            runner._load_sweep_tasks(args, cfg)
    finally:
        Path(sweep_file).unlink()


def test_sweep_key_not_found_raises_error():
    """Test that missing sweep key raises FlexLockValidationError."""
    from flexlock.runner import FlexLockRunner
    from flexlock.exceptions import FlexLockValidationError
    
    runner = FlexLockRunner()
    cfg = OmegaConf.create({'model': 'test'})
    
    import argparse
    args = argparse.Namespace(
        sweep_key='nonexistent.key',
        sweep_file=None,
        sweep=None
    )
    
    with pytest.raises(FlexLockValidationError, match="Sweep key.*not found"):
        runner._load_sweep_tasks(args, cfg)


def test_sweep_file_not_found_raises_error():
    """Test that missing sweep file raises FlexLockConfigError."""
    from flexlock.runner import FlexLockRunner
    from flexlock.exceptions import FlexLockConfigError
    
    runner = FlexLockRunner()
    cfg = OmegaConf.create({'model': 'test'})
    
    import argparse
    args = argparse.Namespace(
        sweep_key=None,
        sweep_file='/nonexistent/file.yaml',
        sweep=None
    )
    
    with pytest.raises(FlexLockConfigError, match="Sweep file.*not found"):
        runner._load_sweep_tasks(args, cfg)


# ── --note (Phase A2) ──


def note_target(save_dir=None, lr=0.01):
    """Trivial target used by the --note runner tests."""
    return {"lr": lr}


def test_note_flag_recorded_in_run_lock(tmp_path):
    """`--note` writes a top-level note: key into run.lock."""
    import yaml as _yaml

    runner = FlexLockRunner()
    out = tmp_path / "run"
    runner.run([
        "-o", "_target_=tests.test_runner.note_target",
        "-o", f"save_dir={out}",
        "--note", "baseline",
    ])
    lock = _yaml.safe_load((out / "run.lock").read_text())
    assert lock["note"] == "baseline"


def test_no_note_means_no_note_key(tmp_path):
    """Without --note the run.lock carries no note key (readers get None)."""
    import yaml as _yaml

    runner = FlexLockRunner()
    out = tmp_path / "run"
    runner.run([
        "-o", "_target_=tests.test_runner.note_target",
        "-o", f"save_dir={out}",
    ])
    lock = _yaml.safe_load((out / "run.lock").read_text())
    assert "note" not in lock
    assert lock.get("note") is None
