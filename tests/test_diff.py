import pytest
from flexlock.diff import RunDiff


def test_rundiff_compare_git_match():
    """Test that RunDiff compares git tree hashes correctly."""
    current = {
        "repos": {
            "main": {"tree": "abc123", "commit": "def456", "is_dirty": False}
        }
    }
    target = {
        "repos": {
            "main": {"tree": "abc123", "commit": "ghi789", "is_dirty": False}
        }
    }
    
    diff = RunDiff(current, target)
    result = diff.compare_git()
    
    assert result is True
    assert "git" not in diff.diffs  # No differences should be recorded


def test_rundiff_compare_git_mismatch():
    """Test that RunDiff detects git differences."""
    current = {
        "repos": {
            "main": {"tree": "abc123", "commit": "def456", "is_dirty": False}
        }
    }
    target = {
        "repos": {
            "main": {"tree": "xyz789", "commit": "ghi789", "is_dirty": False}
        }
    }
    
    diff = RunDiff(current, target)
    result = diff.compare_git()
    
    assert result is False
    assert "git" in diff.diffs
    assert "Repo main: Content changed" in diff.diffs["git"]


def test_rundiff_compare_git_missing_repo():
    """Test that RunDiff handles missing repos."""
    current = {
        "repos": {
            "main": {"tree": "abc123", "commit": "def456", "is_dirty": False}
        }
    }
    target = {
        "repos": {
            "other": {"tree": "abc123", "commit": "ghi789", "is_dirty": False}
        }
    }
    
    diff = RunDiff(current, target)
    result = diff.compare_git()
    
    assert result is False
    assert "git" in diff.diffs
    assert "Repo main missing" in diff.diffs["git"]


def test_rundiff_compare_config_match():
    """Test that RunDiff compares configs correctly."""
    current = {
        "config": {"param1": 1, "save_dir": "/tmp", "timestamp": "2023-01-01"}
    }
    target = {
        "config": {"param1": 1, "save_dir": "/different/path", "timestamp": "2023-01-02"}
    }
    
    diff = RunDiff(current, target)
    result = diff.compare_config()
    
    assert result is True
    assert "config" not in diff.diffs  # No differences should be recorded


def test_rundiff_compare_config_mismatch():
    """Test that RunDiff detects config differences."""
    current = {
        "config": {"param1": 1, "param2": "value"}
    }
    target = {
        "config": {"param1": 2, "param2": "value"}  # Different param1
    }
    
    diff = RunDiff(current, target)
    result = diff.compare_config()
    
    assert result is False
    assert "config" in diff.diffs


def test_rundiff_compare_data_match():
    """Test that RunDiff compares data hashes correctly."""
    current = {
        "data": {"dataset": "hash123"}
    }
    target = {
        "data": {"dataset": "hash123"}
    }
    
    diff = RunDiff(current, target)
    result = diff.compare_data()
    
    assert result is True
    assert "data" not in diff.diffs


def test_rundiff_compare_data_mismatch():
    """Test that RunDiff detects data differences."""
    current = {
        "data": {"dataset": "hash123"}
    }
    target = {
        "data": {"dataset": "hash456"}  # Different hash
    }
    
    diff = RunDiff(current, target)
    result = diff.compare_data()
    
    assert result is False
    assert "data" in diff.diffs


def test_rundiff_is_match_all_match():
    """Test that is_match returns True when all comparisons match."""
    current = {
        "repos": {
            "main": {"tree": "abc123", "is_dirty": False}
        },
        "config": {"param1": 1},
        "data": {"dataset": "hash123"}
    }
    target = {
        "repos": {
            "main": {"tree": "abc123", "is_dirty": False}
        },
        "config": {"param1": 1},
        "data": {"dataset": "hash123"}
    }
    
    diff = RunDiff(current, target)
    result = diff.is_match()
    
    assert result is True


def test_rundiff_is_match_any_mismatch():
    """Test that is_match returns False when any comparison fails."""
    current = {
        "repos": {
            "main": {"tree": "abc123", "is_dirty": False}
        },
        "config": {"param1": 1},
        "data": {"dataset": "hash123"}
    }
    target = {
        "repos": {
            "main": {"tree": "xyz789", "is_dirty": False}  # Different tree hash
        },
        "config": {"param1": 1},
        "data": {"dataset": "hash123"}
    }
    
    diff = RunDiff(current, target)
    result = diff.is_match()
    
    assert result is False