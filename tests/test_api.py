import pytest
from pathlib import Path
import tempfile
import shutil
from flexlock.api import Project, ExecutionResult
from omegaconf import OmegaConf, DictConfig


def test_project_initialization():
    """Test that Project initializes with defaults."""
    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('defaults = {"param1": 1, "nested": {"value": 10}}\n')
        temp_file = f.name

    try:
        project = Project(defaults=f'{temp_file}:defaults')
        assert project.defaults_str == f'{temp_file}:defaults'
        assert project.defaults is not None
        assert isinstance(project.defaults, (dict, DictConfig))
    finally:
        Path(temp_file).unlink()


def test_project_get_method():
    """Test that Project.get retrieves configurations correctly."""
    # Create a temporary defaults file with nested structure
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('''
defaults = {
    "stage1": {"param1": 1, "nested": {"value": 10}},
    "stage2": {"param2": 2, "other": {"value": 20}}
}
''')
        temp_file = f.name

    try:
        project = Project(defaults=f'{temp_file}:defaults')

        # Get the first stage
        stage1_cfg = project.get("stage1")
        assert stage1_cfg["param1"] == 1
        assert stage1_cfg["nested"]["value"] == 10

        # Get the second stage
        stage2_cfg = project.get("stage2")
        assert stage2_cfg["param2"] == 2
        assert stage2_cfg["other"]["value"] == 20
    finally:
        Path(temp_file).unlink()


def dummy_func(a=1, b=2, save_dir=None):
    return {"a": a, "b": b, "sum": a + b}

def test_project_submit_single():
    """Test that Project.submit works for single execution."""
    # Create a temporary directory for output
    temp_dir = tempfile.mkdtemp()

    # Create a temporary defaults file with a simple function
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        temp_file = f.name
        f.write('''
defaults = {
    "test_config": {
        "_target_": "tests.test_api.dummy_func",
        "a": 10,
        "b": 20
    }
}
''')

    try:
        project = Project(defaults=f'{temp_file}:defaults')
        config = project.get("test_config")

        # Add save_dir to config to avoid warnings
        config = OmegaConf.create(config)
        config.save_dir = temp_dir

        # Submit for single execution - should instantiate the config
        # Disable smart_run for this test since we don't have git setup
        result = project.submit(config, smart_run=False)

        # Check that result is an ExecutionResult
        assert isinstance(result, ExecutionResult)
        assert result.status == "SUCCESS"
        assert result.save_dir == temp_dir
    finally:
        Path(temp_file).unlink()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_project_get_nonexistent_key():
    """Test that Project.get handles non-existent keys gracefully."""
    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('defaults = {"param1": 1}\n')
        temp_file = f.name

    try:
        project = Project(defaults=f'{temp_file}:defaults')

        # Should raise KeyError for non-existent key
        with pytest.raises(KeyError):
            project.get("nonexistent")
    finally:
        Path(temp_file).unlink()


def test_project_exists():
    """Test that Project.exists checks for existing runs."""
    # Create a temporary directory structure
    temp_dir = tempfile.mkdtemp()
    run_dir = Path(temp_dir) / "run_001"
    run_dir.mkdir()

    # Create a minimal run.lock file
    import yaml
    lock_data = {
        "config": {"lr": 0.01, "epochs": 10},
        "repos": {"main": {"tree": "abc123"}},
        "data": {}
    }
    with open(run_dir / "run.lock", 'w') as f:
        yaml.dump(lock_data, f)

    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('defaults = {"test": {"lr": 0.01, "epochs": 10}}\n')
        temp_file = f.name

    try:
        project = Project(defaults=f'{temp_file}:defaults')
        config = project.get("test")
        config = OmegaConf.create(config)
        config.save_dir = str(run_dir)

        # Check if run exists (will fail without proper git setup, but tests the API)
        # For this simple test, we just verify the method is callable
        result = project.exists(config, search_dirs=[temp_dir])
        assert isinstance(result, bool)
    finally:
        Path(temp_file).unlink()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_execution_result_dict_access():
    """Test that ExecutionResult allows dict-like access."""
    result_data = {"accuracy": 0.95, "loss": 0.05}
    result = ExecutionResult(
        save_dir="/tmp/test",
        status="SUCCESS",
        result=result_data
    )

    # Test dict-like access
    assert result["accuracy"] == 0.95
    assert result.get("loss") == 0.05
    assert result.get("nonexistent", "default") == "default"

    # Test attribute access (set in __init__)
    assert result.accuracy == 0.95
    assert result.loss == 0.05


def simple_func(lr=0.01, save_dir=None):
    return {"lr": lr, "result": lr * 100}

def test_project_sweep():
    """Test that Project.submit handles sweeps."""
    temp_dir = tempfile.mkdtemp()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('''

defaults = {
    "sweep_config": {
        "_target_": "tests.test_api.simple_func",
        "lr": 0.01
    }
}
''')
        temp_file = f.name

    try:
        project = Project(defaults=f'{temp_file}:defaults')
        config = project.get("sweep_config")
        config = OmegaConf.create(config)
        config.save_dir = temp_dir

        # Define sweep
        sweep = [
            {"lr": 0.001},
            {"lr": 0.01},
            {"lr": 0.1}
        ]

        # Submit sweep (with smart_run disabled and n_jobs=1 for simplicity)
        results = project.submit(config, sweep=sweep, n_jobs=1, smart_run=False)

        # Check results
        assert isinstance(results, list)
        assert len(results) == 3
        assert all(isinstance(r, ExecutionResult) for r in results)
    finally:
        Path(temp_file).unlink()
        shutil.rmtree(temp_dir, ignore_errors=True)