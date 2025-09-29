import pytest
from git import Repo
from pathlib import Path
from omegaconf import OmegaConf
import yaml

from naga.runlock import runlock

@pytest.fixture
def setup_test_env(tmp_path):
    """
    Sets up a comprehensive test environment in a temporary directory.
    """
    # --- Git Repo Setup ---
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = Repo.init(repo_dir)
    (repo_dir / "README.md").write_text("Initial file")
    repo.index.add(["README.md"])
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    repo.index.commit("Initial commit")

    # --- Data File Setup ---
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "dataset.csv").write_text("col1,col2\n1,2\n3,4")

    # --- Previous Stage Setup ---
    prev_stage_dir = tmp_path / "prev_run"
    prev_stage_dir.mkdir()
    prev_runlock_data = {
        "config": {"param": 10},
        "repos": {"main": "prev_commit_hash"}
    }
    with open(prev_stage_dir / "run.lock", "w") as f:
        yaml.dump(prev_runlock_data, f)

    # --- Save Directory ---
    save_dir = tmp_path / "results"
    save_dir.mkdir()

    return {
        "repo": repo,
        "repo_dir": repo_dir,
        "data_dir": data_dir,
        "prev_stage_dir": prev_stage_dir,
        "save_dir": save_dir,
    }

def test_runlock_basic_creation(setup_test_env):
    """Test basic runlock creation without commits, data, or prevs."""
    env = setup_test_env
    cfg = OmegaConf.create({"param": 1, "save_dir": str(env["save_dir"])})
    
    runlock(config=cfg, commit=False)

    lock_file = env["save_dir"] / "run.lock"
    assert lock_file.exists()
    with open(lock_file, 'r') as f:
        data = yaml.safe_load(f)
    
    assert data["config"]["param"] == 1

def test_runlock_with_data_and_prevs(setup_test_env):
    """Test runlock with data hashing and previous stage loading."""
    env = setup_test_env
    cfg = OmegaConf.create({"param": 2, "save_dir": str(env["save_dir"])})

    runlock(
        config=cfg,
        data={"my_data": str(env["data_dir"] / "dataset.csv")},
        prevs=[str(env["prev_stage_dir"])],
        commit=False
    )

    lock_file = env["save_dir"] / "run.lock"
    assert lock_file.exists()
    with open(lock_file, 'r') as f:
        data = yaml.safe_load(f)

    assert "data" in data
    assert "my_data" in data["data"]
    assert isinstance(data["data"]["my_data"], str)
    assert len(data["data"]["my_data"]) > 0

    assert "prevs" in data
    assert str(env["prev_stage_dir"].resolve()) in data["prevs"]
    assert data["prevs"][str(env["prev_stage_dir"].resolve())]["config"]["param"] == 10

def test_runlock_with_commit_true(setup_test_env):
    """Test that runlock creates a new commit when commit=True."""
    env = setup_test_env
    repo = env["repo"]
    initial_commit = repo.head.commit

    # Make a change to the repo
    (env["repo_dir"] / "new_file.txt").write_text("uncommitted change")

    cfg = OmegaConf.create({"param": 3, "save_dir": str(env["save_dir"])})
    runlock(config=cfg, repos={"main": str(env["repo_dir"])}, commit=True)

    lock_file = env["save_dir"] / "run.lock"
    with open(lock_file, 'r') as f:
        data = yaml.safe_load(f)

    assert "repos" in data
    new_commit_hash = data["repos"]["main"]
    assert new_commit_hash != initial_commit.hexsha
    
    new_commit = repo.commit(new_commit_hash)
    assert "Naga: Auto-snapshot" in new_commit.message

def test_runlock_caller_info(setup_test_env):
    """Test that caller information (module, function, filepath) is captured."""
    env = setup_test_env
    cfg = OmegaConf.create({"param": 5, "save_dir": str(env["save_dir"])})

    # We call runlock from this function, so it should be captured.
    runlock(config=cfg, repos={"test_repo": str(env["repo_dir"])}, commit=False)

    lock_file = env["save_dir"] / "run.lock"
    with open(lock_file, 'r') as f:
        data = yaml.safe_load(f)

    assert "caller" in data
    caller_info = data["caller"]
    
    assert caller_info["module"] == "test_runlock"
    assert caller_info["function"] == "test_runlock_caller_info"
    
    # In some CI/test environments, the test file may not be inside the repo,
    # so we check the filepath name, which is more robust.
    assert Path(caller_info["filepath"]).name == "test_runlock.py"
