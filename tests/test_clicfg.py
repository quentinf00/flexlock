import pytest
from omegaconf import OmegaConf, MISSING
from dataclasses import dataclass
import sys
from unittest.mock import patch
import os

from naga import clicfg

# Define a default config structure for testing
@dataclass
class MyConfig:
    param: int = 1
    nested: dict = MISSING

# Create a dummy main function to be decorated
@clicfg
def main(cfg: MyConfig = OmegaConf.structured(MyConfig)):
    return cfg

@pytest.fixture
def config_files(tmp_path):
    """Create temporary config files for testing."""
    base_path = tmp_path / "base.yaml"
    base_path.write_text("param: 10\nnested:\n  key: value")

    override_path = tmp_path / "override.yaml"
    override_path.write_text("param: 20\nnew_param: added")
    
    exp_path = tmp_path / "exp.yaml"
    exp_path.write_text("defaults:\n  - base\n\nexp1:\n  param: 100\n\nexp2:\n  param: 200")

    return base_path, override_path, exp_path

def test_default_config():
    """Test that the default config is used when no args are provided."""
    with patch.object(sys, 'argv', ['script.py']):
        cfg = main()
        assert cfg.param == 1
        assert OmegaConf.is_missing(cfg, "nested")

def test_config_file(config_files):
    """Test loading a config from a file."""
    base_path, _, _ = config_files
    with patch.object(sys, 'argv', ['script.py', '--config', str(base_path)]):
        cfg = main()
        assert cfg.param == 10
        assert cfg.nested.key == "value"

def test_override_path(config_files):
    """Test overriding a config with another file."""
    base_path, override_path, _ = config_files
    with patch.object(sys, 'argv', ['script.py', '--config', str(base_path), '--overrides_path', str(override_path)]):
        cfg = main()
        assert cfg.param == 20
        assert cfg.nested.key == "value"
        assert cfg.new_param == "added"

def test_dotlist_override(config_files):
    """Test overriding with dotlist arguments."""
    base_path, _, _ = config_files
    with patch.object(sys, 'argv', ['script.py', '--config', str(base_path), '-o', 'param=30', 'nested.key=new_value']):
        cfg = main()
        assert cfg.param == 30
        assert cfg.nested.key == "new_value"

def test_experiment_select(config_files):
    """Test selecting an experiment from a config file."""
    _, _, exp_path = config_files
    # This test requires a slightly different main to handle experiment selection structure
    @clicfg
    def exp_main(cfg = OmegaConf.create()):
        return cfg

    with patch.object(sys, 'argv', ['script.py', '--config', str(exp_path), '--experiment', 'exp1']):
        cfg = exp_main()
        assert cfg.param == 100

def test_all_overrides(config_files):
    """Test the combination of all override mechanisms."""
    base_path, override_path, _ = config_files
    with patch.object(sys, 'argv', [
        'script.py',
        '--config', str(base_path),
        '--overrides_path', str(override_path),
        '-o', 'param=40', 'nested.key=final_value'
    ]):
        cfg = main()
        # Dotlist override should have the highest precedence
        assert cfg.param == 40
        assert cfg.nested.key == "final_value"
        assert cfg.new_param == "added"

def test_ipykernel_ignore():
    """Test that sys.argv is ignored if an ipykernel is detected."""
    # This simulates being in a Jupyter notebook, so CLI args should be ignored
    with patch.object(sys, 'argv', ['.../ipykernel_launcher.py', '-f', 'some_file', '-o', 'param=99']):
        cfg = main()
        assert cfg.param == 1 # Should be the default, not 99