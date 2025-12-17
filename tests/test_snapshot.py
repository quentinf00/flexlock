import pytest
from git import Repo
from pathlib import Path
from omegaconf import OmegaConf
import yaml
from unittest.mock import patch, MagicMock
import tempfile
import os
from loguru import logger
logger.enable("flexlock")
from flexlock.snapshot import snapshot, RunTracker


def test_runtracker_initialization():
    """Test basic RunTracker initialization."""
    save_dir = Path("test_run")
    tracker = RunTracker(save_dir)
    
    assert tracker.save_dir == Path("test_run")
    assert "timestamp" in tracker.data


def test_runtracker_initialization_with_parent():
    """Test RunTracker initialization with parent lock."""
    save_dir = Path("test_run")
    parent_lock = Path("parent_run") / "run.lock"
    tracker = RunTracker(save_dir, parent_lock=parent_lock)
    
    assert tracker.save_dir == Path("test_run")
    assert tracker.parent_lock == parent_lock
    assert "timestamp" in tracker.data
    assert "parent" in tracker.data
    assert tracker.data["parent"] == str(parent_lock)


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


def test_runtracker_record_env_with_parent():
    """Test RunTracker environment recording with parent (should skip)."""
    save_dir = Path("test_run")
    parent_lock = Path("parent_run") / "run.lock"
    tracker = RunTracker(save_dir, parent_lock=parent_lock)
    
    # Mock create_shadow_snapshot function for testing
    with patch("flexlock.snapshot.create_shadow_snapshot") as mock_snapshot:
        mock_snapshot.return_value = {"tree": "mock_tree", "commit": "mock_commit", "is_dirty": False}
        
        tracker.record_env({"main": "/path/to/repo"})
        
        # Should not call create_shadow_snapshot when parent exists
        mock_snapshot.assert_not_called()
        # Should not have repos data
        assert "repos" not in tracker.data


def test_runtracker_add_lineage():
    """Test RunTracker lineage addition."""
    save_dir = Path("test_run")
    tracker = RunTracker(save_dir)
    
    tracker.add_lineage(
        name="upstream_run",
        path="/path/to/upstream",
        info={"config": {"param": "value"}}
    )
    
    assert "lineage" in tracker.data
    assert "upstream_run" in tracker.data["lineage"]
    assert tracker.data["lineage"]["upstream_run"]["path"] == "/path/to/upstream"
    assert tracker.data["lineage"]["upstream_run"]["info"]["config"]["param"] == "value"


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


def test_snapshot_function_with_parent():
    """Test the snapshot function with parent lock."""
    with tempfile.TemporaryDirectory() as tmp:
        save_dir = Path(tmp) / "results"
        save_dir.mkdir()
        parent_lock = Path(tmp) / "parent" / "run.lock"
        parent_lock.parent.mkdir()
        parent_lock.write_text("parent data")
        
        cfg = OmegaConf.create({"param": 1, "save_dir": str(save_dir)})
        
        # Mock dependencies to avoid git operations during test
        with patch("flexlock.snapshot.hash_data") as mock_hash:
            mock_hash.return_value = "mock_data_hash"
            
            snapshot(
                cfg,
                data={"dataset": "/path/to/data"},
                parent_lock=str(parent_lock)
            )
            
            lock_file = save_dir / "run.lock"
            assert lock_file.exists()
            
            with open(lock_file, "r") as f:
                data = yaml.safe_load(f)
                
            assert data["config"]["param"] == 1
            # Should have parent reference
            assert "parent" in data
            assert data["parent"] == str(parent_lock)
            # Should have data but no repos (since we rely on parent)
            assert "data" in data
            assert "repos" not in data
            assert data["data"]["dataset"] == "mock_data_hash"


def test_snapshot_function_custom_save_path():
    """Test the snapshot function with custom save path."""
    with tempfile.TemporaryDirectory() as tmp:
        custom_save_dir = Path(tmp) / "custom_results"
        custom_save_dir.mkdir()
        
        cfg = OmegaConf.create({"param": 1, "save_dir": "/different/path"})
        
        # Mock dependencies to avoid git operations during test
        with patch("flexlock.snapshot.create_shadow_snapshot") as mock_snapshot, \
             patch("flexlock.snapshot.hash_data") as mock_hash:
            
            mock_snapshot.return_value = {"tree": "mock_tree", "commit": "mock_commit", "is_dirty": False}
            mock_hash.return_value = "mock_data_hash"
            
            snapshot(
                cfg,
                repos={"main": "."},
                data={"dataset": "/path/to/data"},
                save_path=str(custom_save_dir)
            )
            
            lock_file = custom_save_dir / "run.lock"
            assert lock_file.exists()
            
            with open(lock_file, "r") as f:
                data = yaml.safe_load(f)
                
            assert data["config"]["param"] == 1


def test_snapshot_function_lineage_discovery():
    """Test the snapshot function with lineage discovery."""
    with tempfile.TemporaryDirectory() as tmp:
        # Create a mock upstream run directory
        upstream_dir = Path(tmp) / "upstream_run"
        upstream_dir.mkdir()
        upstream_lock = upstream_dir / "run.lock"
        upstream_lock.write_text("""
config:
  name: upstream_experiment
git_commit: abc123
timestamp: 2023-01-01T00:00:00
""")
        
        # Create a data file inside the upstream run
        data_file = upstream_dir / "model.pt"
        data_file.write_text("mock model data")
        
        save_dir = Path(tmp) / "results"
        save_dir.mkdir()
        
        cfg = OmegaConf.create({"param": 1, "save_dir": str(save_dir)})
        
        # Mock dependencies to avoid git operations during test
        with patch("flexlock.snapshot.hash_data") as mock_hash, \
             patch("flexlock.snapshot.load_stage_from_path") as mock_load_stage:
            
            mock_hash.return_value = "mock_data_hash"
            mock_load_stage.return_value = {"config": {"name": "upstream_experiment"}, "git_commit": "abc123"}
            
            snapshot(
                cfg,
                data={"model": str(data_file)},
                prevs=[str(data_file)]
            )
            
            lock_file = save_dir / "run.lock"
            assert lock_file.exists()
            
            with open(lock_file, "r") as f:
                data = yaml.safe_load(f)
                
            assert data["config"]["param"] == 1
            # Should have lineage information
            assert "lineage" in data
            assert "upstream_run" in data["lineage"]
            assert data["lineage"]["upstream_run"]["path"] == str(upstream_dir)


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    repo = Repo.init(repo_dir)

    initial_file = repo_dir / "README.md"
    initial_file.write_text("Initial commit")
    repo.index.add([str(initial_file)])
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    repo.index.commit("Initial commit")

    return repo


def test_snapshot_with_real_git(git_repo):
    """Test snapshot with real git repository."""
    repo_dir = Path(git_repo.working_dir)
    
    with tempfile.TemporaryDirectory() as tmp:
        save_dir = Path(tmp) / "results"
        save_dir.mkdir()
        
        cfg = OmegaConf.create({"param": 1, "save_dir": str(save_dir)})
        
        # Create a dummy data file
        data_file = save_dir / "data.txt"
        data_file.write_text("test data")
        
        # Change to repo directory for git operations
        original_cwd = os.getcwd()
        try:
            os.chdir(repo_dir)
            
            snapshot(
                cfg,
                repos={"main": str(repo_dir)},
                data={"dataset": str(data_file)}
            )
            
            lock_file = save_dir / "run.lock"
            assert lock_file.exists()
            
            with open(lock_file, "r") as f:
                data = yaml.safe_load(f)
                
            assert data["config"]["param"] == 1
            assert "repos" in data
            assert "main" in data["repos"]
            assert "tree" in data["repos"]["main"]
            assert "commit" in data["repos"]["main"]
            assert "data" in data
            assert "dataset" in data["data"]
            
        finally:
            os.chdir(original_cwd)


def test_snapshot_no_save_dir():
    """Test snapshot function when save_dir is not in config."""
    cfg = OmegaConf.create({"param": 1})  # No save_dir
    
    # Should return early without error
    result = snapshot(cfg, repos={"main": "."}, data={"dataset": "/path/to/data"})
    assert result is None


def test_runtracker_with_parent_and_lineage():
    """Test RunTracker with both parent and lineage."""
    save_dir = Path("test_run")
    parent_lock = Path("parent_run") / "run.lock"
    tracker = RunTracker(save_dir, parent_lock=parent_lock)
    
    # Add lineage
    tracker.add_lineage(
        name="upstream_run",
        path="/path/to/upstream",
        info={"config": {"param": "value"}}
    )
    
    # Should have both parent and lineage
    assert "parent" in tracker.data
    assert "lineage" in tracker.data
    assert tracker.data["parent"] == str(parent_lock)
    assert "upstream_run" in tracker.data["lineage"]


def test_snapshot_function_with_prevs_from_data():
    """Test that prevs automatically includes data values for lineage discovery."""
    with tempfile.TemporaryDirectory() as tmp:
        # Create a mock upstream run directory
        upstream_dir = Path(tmp) / "upstream_run"
        upstream_dir.mkdir()
        upstream_lock = upstream_dir / "run.lock"
        upstream_lock.write_text("""
config:
  name: upstream_experiment
git_commit: abc123
timestamp: 2023-01-01T00:00:00
""")
        
        # Create a data file inside the upstream run
        data_file = upstream_dir / "model.pt"
        data_file.write_text("mock model data")
        
        save_dir = Path(tmp) / "results"
        save_dir.mkdir()
        
        cfg = OmegaConf.create({"param": 1, "save_dir": str(save_dir)})
        
        # Mock dependencies to avoid git operations during test
        with patch("flexlock.snapshot.hash_data") as mock_hash, \
             patch("flexlock.snapshot.load_stage_from_path") as mock_load_stage:
            
            mock_hash.return_value = "mock_data_hash"
            mock_load_stage.return_value = {"config": {"name": "upstream_experiment"}, "git_commit": "abc123"}
            
            # Only provide data, not explicit prevs - should still discover lineage
            logger.debug("Starting snapshot with data for lineage discovery")
            snapshot(
                cfg,
                data={"model": str(data_file)},
                prevs=[data_file]
            )
            
            lock_file = save_dir / "run.lock"
            assert lock_file.exists()
            
            with open(lock_file, "r") as f:
                data = yaml.safe_load(f)
                
            assert data["config"]["param"] == 1
            # Should have lineage information from data paths
            assert "lineage" in data
            assert "upstream_run" in data["lineage"]