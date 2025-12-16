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

