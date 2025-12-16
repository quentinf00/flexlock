import pytest
from pathlib import Path
import tempfile
from flexlock.api import Project
from omegaconf import OmegaConf


def test_project_initialization():
    """Test that Project initializes with defaults."""
    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('def defaults():\n    return {"param1": 1, "nested": {"value": 10}}\n')
        temp_file = f.name
    
    try:
        project = Project(defaults=f'{temp_file}:defaults')
        assert project.defaults == f'{temp_file}:defaults'
        assert project.runner is not None
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
        assert stage1_cfg.param1 == 1
        assert stage1_cfg.nested.value == 10
        
        # Get the second stage
        stage2_cfg = project.get("stage2")
        assert stage2_cfg.param2 == 2
        assert stage2_cfg.other.value == 20
    finally:
        Path(temp_file).unlink()


def test_project_submit_single():
    """Test that Project.submit works for single execution."""
    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('defaults = {"_target_": "builtins.dict", "a": 1, "b": 2}\n')
        temp_file = f.name

    try:
        project = Project(defaults=f'{temp_file}:defaults')
        config = project.get("")  # Get the root config

        # Submit for single execution - should instantiate the config
        result = project.submit(config)

        # Check that instantiation worked
        assert isinstance(result, dict)
        assert result['a'] == 1
        assert result['b'] == 2
    finally:
        Path(temp_file).unlink()


def test_project_get_nonexistent_key():
    """Test that Project.get handles non-existent keys gracefully."""
    # Create a temporary defaults file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write('defaults = {"param1": 1}\n')
        temp_file = f.name
    
    try:
        project = Project(defaults=f'{temp_file}:defaults')
        
        assert  project.get("nonexistent.key") is None
    finally:
        Path(temp_file).unlink()