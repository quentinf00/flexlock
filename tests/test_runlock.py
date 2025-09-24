import pytest
from git import Repo
import os
from pathlib import Path
from omegaconf import OmegaConf, MISSING
from dataclasses import dataclass
import yaml
import sys
from unittest.mock import patch

from naga import clicfg, snapshot, runlock

# Define a config structure for testing the full stack
@dataclass
class FullConfig:
    save_dir: str = MISSING
    param: int = 1

# Create a dummy main function with the full decorator stack
# Note the order: runlock is first to intercept the final config
@clicfg
@snapshot(branch="runlock_test")
@runlock
def full_main(cfg: FullConfig = OmegaConf.structured(FullConfig)):
    return f"Finished with param: {cfg.param}"

@pytest.fixture
def git_repo_for_runlock(tmp_path):
    """Setup a git repo for the runlock test."""
    repo_dir = tmp_path / "runlock_repo"
    repo_dir.mkdir()
    repo = Repo.init(repo_dir)
    
    initial_file = repo_dir / "config.yaml"
    initial_file.write_text("param: 10")
    repo.index.add([str(initial_file)])
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    repo.index.commit("Initial commit")
    
    return repo, repo_dir

def test_runlock_creation(git_repo_for_runlock):
    """
    Test that the full decorator stack correctly creates a run.lock file
    with config and git commit information.
    """
    repo, repo_dir = git_repo_for_runlock
    save_dir = repo_dir / "results"
    
    # Create a file to be committed by the snapshot decorator
    (repo_dir / "new_file.txt").write_text("content")

    # Simulate running from the command line
    os.chdir(repo_dir)
    with patch.object(sys, 'argv', [
        'script.py',
        '-o', f'save_dir={save_dir}', 'param=100'
    ]):
        result = full_main()

    # --- Assertions ---
    assert result == "Finished with param: 100"
    
    # 1. Check the run.lock file exists and has the correct content
    lock_file = save_dir / "run.lock"
    assert lock_file.exists()
    
    with open(lock_file, 'r') as f:
        run_data = yaml.safe_load(f)

    # 2. Check the config section
    assert run_data["config"]["param"] == 100
    assert run_data["config"]["save_dir"] == str(save_dir)

    # 3. Check the git_commit from the snapshot decorator
    assert "git_commit" in run_data
    
    # 4. Verify the commit in the actual git repo
    commit_hash = run_data["git_commit"]
    commit = repo.commit(commit_hash)
    assert commit is not None
    assert commit.message.strip() == "Naga: Auto-snapshot"
