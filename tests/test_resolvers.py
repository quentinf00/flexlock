import pytest
from omegaconf import OmegaConf
from pathlib import Path
import time

from flexlock.resolvers import now_resolver, vinc_resolver
from flexlock import config


def test_now_resolver():
    """Test the now_resolver returns a string in the correct format."""
    # Test default format
    timestamp = now_resolver()
    assert isinstance(timestamp, str)
    try:
        time.strptime(timestamp, config.TIMESTAMP_FORMAT)
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
    path1 = vinc_resolver(str(base_path))
    assert path1 == str(tmp_path / "experiment_0000")
    Path(path1).mkdir()

    # Second call, should return experiment_0001
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
    path1 = vinc_resolver(str(base_path), fmt=fmt)
    assert path1 == str(tmp_path / "run-v00")
    Path(path1).mkdir()

    # Second call
    path2 = vinc_resolver(str(base_path), fmt=fmt)
    assert path2 == str(tmp_path / "run-v01")


def test_latest_resolver(tmp_path):
    """Test the latest_resolver returns the most recently modified path."""
    from flexlock.resolvers import latest_resolver
    import time

    # Create test directories with different modification times
    dir1 = tmp_path / "results_0001"
    dir2 = tmp_path / "results_0002"
    dir3 = tmp_path / "results_0003"

    # Create in sequence to ensure different modification times
    dir1.mkdir()
    time.sleep(0.01)  # Small delay to ensure different timestamp
    dir2.mkdir()
    time.sleep(0.01)  # Small delay to ensure different timestamp
    dir3.mkdir()

    # Test with glob pattern
    pattern = str(tmp_path / "results_*")
    latest = latest_resolver(pattern)

    # Should return the most recently created/modified directory
    assert latest == str(dir3)


def test_latest_resolver_with_files(tmp_path):
    """Test the latest_resolver works with files too."""
    from flexlock.resolvers import latest_resolver
    import time

    # Create test files with different modification times
    file1 = tmp_path / "data_v1.txt"
    file2 = tmp_path / "data_v2.txt"
    file3 = tmp_path / "data_v3.txt"

    # Create files in sequence
    file1.write_text("content1")
    time.sleep(0.01)
    file2.write_text("content2")
    time.sleep(0.01)
    file3.write_text("content3")

    # Test with glob pattern
    pattern = str(tmp_path / "data_v*.txt")
    latest = latest_resolver(pattern)

    # Should return the most recently created/modified file
    assert latest == str(file3)


def test_latest_resolver_no_matches():
    """Test the latest_resolver returns the pattern when no matches are found."""
    from flexlock.resolvers import latest_resolver

    # Use a pattern that won't match anything
    pattern = "/nonexistent/directory/*.txt"
    result = latest_resolver(pattern)

    # Should return the original pattern when no matches
    assert result == pattern


def test_latest_resolver_with_globbing_patterns(tmp_path):
    """Test latest_resolver with different globbing patterns."""
    from flexlock.resolvers import latest_resolver
    import time

    # Create a nested directory structure
    subdir1 = tmp_path / "subdir1"
    subdir2 = tmp_path / "subdir2"
    subdir1.mkdir()
    subdir2.mkdir()

    # Create files in both subdirectories
    file1 = subdir1 / "file.txt"
    file2 = subdir2 / "file.txt"
    file1.write_text("content1")
    time.sleep(0.01)
    file2.write_text("content2")

    # Use recursive pattern
    pattern = str(tmp_path / "**" / "file.txt")
    latest = latest_resolver(pattern)

    # Should return the most recently created file
    assert latest == str(file2)
