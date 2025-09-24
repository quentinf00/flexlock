
import pytest
from pathlib import Path
from omegaconf import OmegaConf
from dataclasses import dataclass

from naga.data_hash import hash_data
from naga.track_data import track_data
from naga.context import run_context

@pytest.fixture
def test_data(tmp_path):
    """Create some test files and directories for hashing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    file1 = data_dir / "file1.txt"
    file1.write_text("hello")
    
    sub_dir = data_dir / "sub"
    sub_dir.mkdir()
    
    file2 = sub_dir / "file2.log"
    file2.write_text("world")
    
    return data_dir, file1

def test_hash_data_file(test_data):
    """Test hashing a single file."""
    _, file1_path = test_data
    file_hash = hash_data(file1_path)
    assert isinstance(file_hash, str)
    assert len(file_hash) == 16  # xxhash.xxh3_64 produces a 16-char hex digest

def test_hash_data_directory(test_data):
    """Test hashing a directory."""
    data_dir, _ = test_data
    dir_hash = hash_data(data_dir)
    assert isinstance(dir_hash, str)
    
    # Verify that the hash changes when a file is modified
    (data_dir / "file1.txt").write_text("changed")
    new_dir_hash = hash_data(data_dir)
    assert dir_hash != new_dir_hash

def test_track_data_decorator(test_data):
    """Test that the @track_data decorator correctly hashes specified paths."""
    data_dir, file1_path = test_data

    @dataclass
    class DataConfig:
        my_data_dir: str = str(data_dir)
        my_data_file: str = str(file1_path)

    @track_data("my_data_dir", "my_data_file")
    def my_data_function(cfg: DataConfig):
        pass

    # Reset context for a clean test
    run_context.set({})
    
    cfg = OmegaConf.structured(DataConfig)
    my_data_function(cfg)

    context_data = run_context.get()
    assert "data_hashes" in context_data
    
    # Check that the hashes were computed and stored correctly
    expected_dir_hash = hash_data(data_dir)
    expected_file_hash = hash_data(file1_path)
    
    assert context_data["data_hashes"]["my_data_dir"] == expected_dir_hash
    assert context_data["data_hashes"]["my_data_file"] == expected_file_hash
