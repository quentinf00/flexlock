
import pytest
from git import Repo
import os
from pathlib import Path

from naga import snapshot

@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    repo = Repo.init(repo_dir)
    
    # Initial commit is required to have a HEAD
    initial_file = repo_dir / "README.md"
    initial_file.write_text("Initial commit")
    repo.index.add([str(initial_file)])
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    repo.index.commit("Initial commit")
    
    return repo

def test_snapshot_basic(git_repo):
    """Test that a basic snapshot captures new and modified files."""
    repo_dir = Path(git_repo.working_dir)
    
    # Create a new file and modify an existing one
    (repo_dir / "new_file.txt").write_text("new content")
    (repo_dir / "README.md").write_text("modified content")

    @snapshot(branch="test_branch", message="Test basic commit")
    def my_function():
        pass

    # Run in the repo directory
    os.chdir(repo_dir)
    my_function()

    # Assertions
    test_branch = git_repo.heads["test_branch"]
    last_commit = test_branch.commit
    
    assert last_commit.message.strip() == "Test basic commit"
    assert len(last_commit.parents) == 1
    
    # Check that both new and modified files are in the commit
    committed_files = last_commit.stats.files.keys()
    assert "new_file.txt" in committed_files
    assert "README.md" in committed_files

def test_snapshot_exclude(git_repo):
    """Test that the exclude filter prevents files from being committed."""
    repo_dir = Path(git_repo.working_dir)
    
    (repo_dir / "script.py").write_text("print('hello')")
    (repo_dir / "data.log").write_text("log entry")

    @snapshot(branch="exclude_branch", exclude=["*.log"])
    def my_function():
        pass

    os.chdir(repo_dir)
    my_function()

    last_commit = git_repo.heads["exclude_branch"].commit
    committed_files = last_commit.stats.files.keys()
    
    assert "script.py" in committed_files
    assert "data.log" not in committed_files

def test_snapshot_include(git_repo):
    """Test that the include filter only commits specified files."""
    repo_dir = Path(git_repo.working_dir)
    
    (repo_dir / "script.py").write_text("print('hello')")
    (repo_dir / "README.md").write_text("docs")

    @snapshot(branch="include_branch", include=["*.py"])
    def my_function():
        pass

    os.chdir(repo_dir)
    my_function()

    last_commit = git_repo.heads["include_branch"].commit
    committed_files = last_commit.stats.files.keys()
    
    assert "script.py" in committed_files
    assert "README.md" not in committed_files
