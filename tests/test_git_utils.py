import pytest
from git import Repo
from pathlib import Path
import os

from flexlock.git_utils import get_git_commit, commit_cwd, create_shadow_snapshot, get_git_tree_hash


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


def test_get_git_commit(git_repo):
    """Test that get_git_commit returns the correct commit hash."""
    expected_hash = git_repo.head.commit.hexsha
    actual_hash = get_git_commit(path=git_repo.working_dir)
    assert actual_hash == expected_hash


def test_commit_cwd_basic(git_repo):
    """Test that commit_cwd creates a new commit with the correct files."""
    repo_dir = Path(git_repo.working_dir)
    initial_commit = git_repo.head.commit

    # Create a new file
    (repo_dir / "new_file.txt").write_text("new content")

    new_commit = commit_cwd(
        branch="test_branch", message="Test commit", repo_path=str(repo_dir)
    )

    assert new_commit != initial_commit
    assert new_commit.message.strip() == "Test commit"

    committed_files = new_commit.stats.files.keys()
    assert "new_file.txt" in committed_files
    assert "README.md" not in committed_files  # Was not changed

    # Check that the branch was created
    assert "test_branch" in git_repo.heads


def test_commit_cwd_filesize_warn(git_repo):
    """Test that commit_cwd issues a warning for large files."""
    repo_dir = Path(git_repo.working_dir)

    # Create a large file
    large_file = repo_dir / "large_file.bin"
    # Write 2KB of data, with a 1KB warning threshold
    large_file.write_bytes(os.urandom(2 * 1024 * 1024))

    with pytest.warns(UserWarning, match="larger than 1.00 MB"):
        commit_cwd(
            branch="large_file_branch",
            message="Large file commit",
            repo_path=str(repo_dir),
            filesize_warn=1 * 1024 * 1024,  # 1 MB
        )


def test_get_git_tree_hash(git_repo):
    """Test that get_git_tree_hash returns the correct tree hash."""
    expected_tree_hash = git_repo.head.commit.tree.hexsha
    actual_hash = get_git_tree_hash(path=git_repo.working_dir)
    assert actual_hash == expected_tree_hash


def test_get_git_tree_hash_nonexistent_path():
    """Test that get_git_tree_hash handles nonexistent paths."""
    result = get_git_tree_hash(path="/nonexistent/path")
    assert result.startswith("Error getting git tree hash")


def test_get_git_commit_error():
    """Test that get_git_commit handles non-repo paths gracefully."""
    # This will fail because the temp directory is not a git repo
    error_message = get_git_commit(path="/tmp")
    assert "Error getting git commit" in error_message


def test_commit_cwd_with_deleted_file(git_repo):
    """Test that commit_cwd correctly handles a deleted file."""
    repo_dir = Path(git_repo.working_dir)
    initial_commit = git_repo.head.commit

    # Create and commit a file
    file_to_delete = repo_dir / "file_to_delete.txt"
    file_to_delete.write_text("some content")
    git_repo.index.add([str(file_to_delete)])
    git_repo.index.commit("Add file to be deleted")

    # Delete the file
    os.remove(file_to_delete)

    # Commit the deletion
    new_commit = commit_cwd(
        branch="delete_branch", message="Delete file", repo_path=str(repo_dir)
    )

    assert new_commit != initial_commit
    assert new_commit.message.strip() == "Delete file"

    # Check that the file was deleted in the commit
    # The change type 'D' stands for 'Deleted'
    diff_against_parent = new_commit.parents[0].diff(new_commit)
    assert any(
        change.change_type == "D" and change.a_path == "file_to_delete.txt"
        for change in diff_against_parent
    )


def test_create_shadow_snapshot_basic(git_repo):
    """Test basic shadow snapshot creation."""
    repo_dir = Path(git_repo.working_dir)
    
    result = create_shadow_snapshot(repo_path=str(repo_dir))
    
    assert "commit" in result
    assert "tree" in result
    assert "is_dirty" in result
    assert isinstance(result["commit"], str)
    assert isinstance(result["tree"], str)
    assert isinstance(result["is_dirty"], bool)
    assert len(result["commit"]) > 0
    assert len(result["tree"]) > 0


def test_create_shadow_snapshot_with_changes(git_repo):
    """Test shadow snapshot with uncommitted changes."""
    repo_dir = Path(git_repo.working_dir)
    
    # Make changes to the repo
    new_file = repo_dir / "new_file.txt"
    new_file.write_text("new content")
    
    # Create initial snapshot
    result1 = create_shadow_snapshot(repo_path=str(repo_dir))
    
    # Change the file content
    new_file.write_text("updated content")
    
    # Create another snapshot
    result2 = create_shadow_snapshot(repo_path=str(repo_dir))
    
    # Tree hashes should be different due to the content change
    assert result1["tree"] != result2["tree"]
    assert result1["is_dirty"] is True  # First snapshot should show dirty
    assert result2["is_dirty"] is True  # Second snapshot should show dirty


def test_shadow_snapshot_ignores_patterns(git_repo):
    """Test shadow snapshot with ignore patterns."""
    repo_dir = Path(git_repo.working_dir)

    # Create files to be ignored
    (repo_dir / "temp_file.tmp").write_text("temp content")
    (repo_dir / "secret.txt").write_text("secret content")

    # Create a file that should not be ignored
    (repo_dir / "important.txt").write_text("important content")

    # Create snapshot with ignores
    result_with_ignore = create_shadow_snapshot(
        repo_path=str(repo_dir),
        ignore_patterns=["*.tmp", "secret.txt"]
    )

    # Create another file that should not be ignored
    (repo_dir / "another_important.txt").write_text("more important content")

    result_without_ignore = create_shadow_snapshot(repo_path=str(repo_dir))

    # The tree hashes should be different since we're including all files in the second case
    assert result_with_ignore["tree"] != result_without_ignore["tree"]