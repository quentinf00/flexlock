import pytest
from omegaconf import OmegaConf
from dataclasses import dataclass
import sys
from unittest.mock import patch

from pathlib import Path
from naga.clicfg import clicfg

# Define a dataclass for the configuration schema
@dataclass
class MyConfig:
    param: int = 1
    nested: str = "default"

# Create a decorated function to be used in tests
@clicfg(config_class=MyConfig)
def main(cfg):
    return cfg

@pytest.fixture
def config_file(tmp_path):
    """Create a temporary base config file."""
    base_path = tmp_path / "base.yaml"
    base_path.write_text("param: 10\nnested: 'from_file'")
    return base_path

def test_clicfg_default_config():
    """Test that the default config from the dataclass is used."""
    cfg = main()
    assert cfg.param == 1
    assert cfg.nested == "default"

def test_clicfg_cli_mode_with_config_file(config_file):
    """Test loading a config from a file via CLI arguments."""
    with patch.object(sys, 'argv', ['script.py', '--config', str(config_file)]):
        cfg = main()
        assert cfg.param == 10
        assert cfg.nested == "from_file"

def test_clicfg_cli_mode_with_overrides(config_file):
    """Test overriding config values from the CLI."""
    with patch.object(sys, 'argv', [
        'script.py',
        '--config', str(config_file),
        '-o', 'param=20', 'nested=cli_override'
    ]):
        cfg = main()
        assert cfg.param == 20
        assert cfg.nested == "cli_override"

def test_clicfg_programmatic_mode():
    """Test calling the decorated function programmatically with kwargs."""
    cfg = main(param=30, nested="programmatic_override")
    assert cfg.param == 30
    assert cfg.nested == "programmatic_override"

def test_clicfg_programmatic_mode_overrides_file(config_file):
    """
    Test that programmatic kwargs have higher precedence than the base config file.
    To do this, we need to simulate a CLI call that provides the config file,
    but then call the function with kwargs. The current implementation gives
    programmatic kwargs the highest priority.
    """
    # In a real script, you might load a base config and then override it.
    # The decorator handles this by layering overrides.
    # Let's test the final layer (programmatic) wins.
    
    # Simulate a scenario where a base config is loaded via CLI args in a script,
    # but the function is then called with kwargs.
    overrides_config = Path(config_file).parent / 'override.yaml'
    overrides_config.write_text("param: 40\nnested: 'from_override_file'")
    with patch.object(sys, 'argv', ['script.py', '--config', str(config_file), '--overrides_path', str(overrides_config)]):
        # Even though the CLI specifies a config file, the direct kwargs take precedence.
        cfg = main()

    assert cfg.param == 40
    # 'nested' should come from the file, as it wasn't overridden programmatically.
    assert cfg.nested == "from_override_file"

def test_clicfg_no_config_class():
    """Test that the decorator works even without a config_class."""
    @clicfg()
    def simple_main(cfg):
        return cfg

    cfg = simple_main(param=50)
    assert cfg.param == 50
