import pytest
from omegaconf import OmegaConf
from pathlib import Path
import time

from flexlock.resolvers import now_resolver, vinc_resolver, resolver_context

def test_now_resolver():
    """Test the now_resolver returns a string in the correct format."""
    # Test default format
    timestamp = now_resolver()
    assert isinstance(timestamp, str)
    try:
        time.strptime(timestamp, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        pytest.fail("Default timestamp format is incorrect")

    # Test custom format
    timestamp_custom = now_resolver(fmt="%Y%m%d")
    assert isinstance(timestamp_custom, str)
    try:
        time.strptime(timestamp_custom, "%Y%m%d")
    except ValueError:
        pytest.fail("Custom timestamp format is incorrect")

def test_vinc_resolver(tmp_path):
    """Test the vinc_resolver correctly increments version numbers."""
    base_path = tmp_path / "experiment"

    # First call, should return experiment_0000
    with resolver_context():
        path1 = vinc_resolver(str(base_path))
    assert path1 == str(tmp_path / "experiment_0000")
    Path(path1).mkdir()

    # Second call, should return experiment_0001
    with resolver_context():
        path2 = vinc_resolver(str(base_path))
    assert path2 == str(tmp_path / "experiment_0001")
    Path(path2).mkdir()

    # Create a file with a higher version number manually
    (tmp_path / "experiment_0005").mkdir()

    # Next call should be experiment_0006
    path3 = vinc_resolver(str(base_path))
    assert path3 == str(tmp_path / "experiment_0006")

def test_vinc_resolver_with_custom_format(tmp_path):
    """Test vinc_resolver with a custom format string."""
    base_path = tmp_path / "run"
    fmt = "-v{i:02d}"

    # First call
    with resolver_context():
        path1 = vinc_resolver(str(base_path), fmt=fmt)
    assert path1 == str(tmp_path / "run-v00")
    Path(path1).mkdir()

    # Second call
    with resolver_context():
        path2 = vinc_resolver(str(base_path), fmt=fmt)
    assert path2 == str(tmp_path / "run-v01")
