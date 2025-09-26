import pytest
from pathlib import Path
from omegaconf import OmegaConf
from dataclasses import dataclass
import time
import os
from unittest.mock import patch, call

from naga.data_hash import hash_data, _load_cache
from naga.track_data import track_data
from naga.context import run_context

# --- Fixtures ---

@pytest.fixture(autouse=True)
def clear_cache_before_each_test(tmp_path):
    """Fixture to ensure the cache is clear and isolated for each test."""
    cache_dir = tmp_path / ".cache" / "naga"
    cache_file = cache_dir / "hashes.json"
    
    with patch('naga.data_hash.CACHE_FILE', cache_file):
        if cache_file.exists():
            os.remove(cache_file)
        yield
        if cache_file.exists():
            os.remove(cache_file)

@pytest.fixture
def test_data(tmp_path):
    """Create a standard small test directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file1.txt").write_text("hello")
    sub_dir = data_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "file2.log").write_text("world")
    return data_dir

# --- Basic Tests ---

def test_hash_data_file(test_data):
    """Test hashing a single file."""
    file_path = test_data / "file1.txt"
    file_hash = hash_data(file_path)
    assert isinstance(file_hash, str) and len(file_hash) == 16

def test_hash_data_directory(test_data):
    """Test hashing a directory and that it changes on modification."""
    dir_hash1 = hash_data(test_data)
    assert isinstance(dir_hash1, str)
    
    (test_data / "file1.txt").write_text("changed")
    dir_hash2 = hash_data(test_data)
    assert dir_hash1 != dir_hash2

# --- Caching Logic Tests ---

def test_hash_caching_file(test_data):
    """Verify that a file hash is cached and reused."""
    file_path = test_data / "file1.txt"
    hash1 = hash_data(file_path)
    cache = _load_cache()
    assert str(file_path.resolve()) in cache
    hash2 = hash_data(file_path)
    assert hash1 == hash2

def test_hash_caching_file_invalidation(test_data):
    """Verify that modifying a file invalidates the cache."""
    file_path = test_data / "file1.txt"
    hash1 = hash_data(file_path)
    time.sleep(0.01) # Ensure mtime is different
    file_path.write_text("new content")
    hash2 = hash_data(file_path)
    assert hash1 != hash2

def test_small_dir_cache_invalidation_by_content(test_data):
    """Test that changing a file's content in a small dir invalidates the cache."""
    hash1 = hash_data(test_data)
    time.sleep(0.01)
    # Modify a nested file. This should change the 'latest_mtime'.
    (test_data / "sub" / "file2.log").write_text("new world")
    hash2 = hash_data(test_data)
    assert hash1 != hash2

def test_small_dir_cache_invalidation_by_add_file(test_data):
    """Test that adding a file to a small dir invalidates the cache."""
    hash1 = hash_data(test_data)
    (test_data / "new_file.txt").write_text("a new file")
    hash2 = hash_data(test_data)
    assert hash1 != hash2

def test_large_dir_fallback_caching(tmp_path, monkeypatch):
    """Test that large directories fall back to simple mtime caching."""
    monkeypatch.setenv("NAGA_CACHE_DIR_FILE_LIMIT", "5")
    large_dir = tmp_path / "large_dir"
    large_dir.mkdir()
    for i in range(10):
        (large_dir / f"file{i}.txt").write_text(str(i))

    # Mock logger to check for the warning
    with patch('naga.data_hash.log') as mock_log:
        hash1 = hash_data(large_dir)
        # Second call should be a cache hit based on mtime
        hash2 = hash_data(large_dir)
        assert hash1 == hash2
        mock_log.warning.assert_called_once()

    # Now, modify a file inside without touching the parent dir's mtime
    time.sleep(0.01)
    (large_dir / "file3.txt").write_text("changed")
    
    # The hash should NOT change because we are in fallback mode
    hash3 = hash_data(large_dir)
    assert hash1 == hash3

    # But if we touch the parent directory, it should invalidate
    time.sleep(0.01)
    large_dir.touch()
    hash4 = hash_data(large_dir)
    assert hash1 != hash4

def test_cache_dir_file_limit_env_var(tmp_path, monkeypatch):
    """Test that the NAGA_CACHE_DIR_FILE_LIMIT env var is respected."""
    monkeypatch.setenv("NAGA_CACHE_DIR_FILE_LIMIT", "2")
    
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    (test_dir / "f1").touch()
    (test_dir / "f2").touch()

    # With 2 files, should use the detailed stats (count=2, latest_mtime)
    hash_data(test_dir)
    cache = _load_cache()
    stats = cache[str(test_dir.resolve())]['stats']
    assert "file_count" in stats and stats["file_count"] == 2

    # Add a third file, exceeding the limit of 2
    (test_dir / "f3").touch()
    hash_data(test_dir)
    cache = _load_cache()
    stats = cache[str(test_dir.resolve())]['stats']
    # Should now have fallen back to the simple mtime cache
    assert "mtime" in stats and "file_count" not in stats

def test_naga_no_cache_env_variable(test_data, monkeypatch):
    """Test that NAGA_NO_CACHE=1 disables the cache."""
    monkeypatch.setenv("NAGA_NO_CACHE", "1")
    hash_data(test_data)
    cache = _load_cache()
    assert not cache # Cache should be empty

# --- Decorator Test ---

def test_track_data_decorator(test_data):
    """Test that the @track_data decorator correctly hashes specified paths."""
    @dataclass
    class DataConfig:
        my_data_dir: str = str(test_data)

    @track_data("my_data_dir")
    def my_data_function(cfg: DataConfig):
        pass

    run_context.set({})
    my_data_function(OmegaConf.structured(DataConfig))
    context_data = run_context.get()
    
    assert "data_hashes" in context_data
    assert context_data["data_hashes"]["my_data_dir"] == hash_data(test_data)