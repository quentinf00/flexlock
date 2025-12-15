import pytest
from git import Repo
from pathlib import Path
from omegaconf import OmegaConf
import yaml
from unittest.mock import patch
import tempfile

from flexlock.snapshot import snapshot, RunTracker


def test_runtracker_initialization():
    """Test basic RunTracker initialization."""
    save_dir = Path("test_run")
    tracker = RunTracker(save_dir)
    
    assert tracker.save_dir == Path("test_run")
    assert "timestamp" in tracker.data


def test_runtracker_record_data():
    """Test RunTracker data recording."""
    save_dir = Path("test_run")
    tracker = RunTracker(save_dir)
    
    # Mock hash_data function for testing
    with patch("flexlock.snapshot.hash_data") as mock_hash:
        mock_hash.return_value = "mock_hash_value"
        
        tracker.record_data({"dataset": "/path/to/data"})
        
        assert tracker.data["data"]["dataset"] == "mock_hash_value"
        mock_hash.assert_called_once_with("/path/to/data")


def test_runtracker_record_env():
    """Test RunTracker environment recording."""
    save_dir = Path("test_run")
    tracker = RunTracker(save_dir)
    
    # Mock create_shadow_snapshot function for testing
    with patch("flexlock.snapshot.create_shadow_snapshot") as mock_snapshot:
        mock_snapshot.return_value = {"tree": "mock_tree", "commit": "mock_commit", "is_dirty": False}
        
        tracker.record_env({"main": "/path/to/repo"})
        
        assert tracker.data["repos"]["main"]["tree"] == "mock_tree"
        assert tracker.data["repos"]["main"]["commit"] == "mock_commit"
        assert tracker.data["repos"]["main"]["is_dirty"] == False
        mock_snapshot.assert_called_once_with("/path/to/repo")


def test_runtracker_save():
    """Test RunTracker save functionality."""
    with tempfile.TemporaryDirectory() as tmp:
        save_dir = Path(tmp) / "results"
        save_dir.mkdir()
        
        tracker = RunTracker(save_dir)
        config = OmegaConf.create({"param1": 1, "param2": "test"})
        
        # Mock the save method to avoid git operations during test
        with patch("flexlock.snapshot.create_shadow_snapshot") as mock_snapshot:
            mock_snapshot.return_value = {"tree": "mock_tree", "commit": "mock_commit", "is_dirty": False}
            
            tracker.record_env({"main": "."})
            tracker.save(config)
            
            lock_file = save_dir / "run.lock"
            assert lock_file.exists()
            
            with open(lock_file, "r") as f:
                data = yaml.safe_load(f)
                
            assert data["config"]["param1"] == 1
            assert data["config"]["param2"] == "test"
            assert "timestamp" in data


def test_snapshot_function_basic():
    """Test the snapshot function."""
    with tempfile.TemporaryDirectory() as tmp:
        save_dir = Path(tmp) / "results"
        save_dir.mkdir()
        
        cfg = OmegaConf.create({"param": 1, "save_dir": str(save_dir)})
        
        # Mock dependencies to avoid git operations during test
        with patch("flexlock.snapshot.create_shadow_snapshot") as mock_snapshot, \
             patch("flexlock.snapshot.hash_data") as mock_hash:
            
            mock_snapshot.return_value = {"tree": "mock_tree", "commit": "mock_commit", "is_dirty": False}
            mock_hash.return_value = "mock_data_hash"
            
            snapshot(cfg, repos={"main": "."}, data={"dataset": "/path/to/data"})
            
            lock_file = save_dir / "run.lock"
            assert lock_file.exists()
            
            with open(lock_file, "r") as f:
                data = yaml.safe_load(f)
                
            assert data["config"]["param"] == 1
            # Check that both repos and data were recorded
            assert "repos" in data
            assert "data" in data
            assert data["data"]["dataset"] == "mock_data_hash"