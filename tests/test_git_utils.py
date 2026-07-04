import pytest
from git import Repo
from pathlib import Path
import os

from flexlock.git_utils import (
    get_git_commit,
    create_shadow_snapshot,
    create_shadow_tree,
    get_git_tree_hash,
)
from flexlock.exceptions import FlexLockSnapshotError


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




def test_get_git_tree_hash(git_repo):
    """Test that get_git_tree_hash returns the correct tree hash."""
    expected_tree_hash = git_repo.head.commit.tree.hexsha
    actual_hash = get_git_tree_hash(path=git_repo.working_dir)
    assert actual_hash == expected_tree_hash


def test_get_git_tree_hash_nonexistent_path():
    """A non-repo path raises rather than returning an error string."""
    with pytest.raises(FlexLockSnapshotError):
        get_git_tree_hash(path="/nonexistent/path")


def test_get_git_commit_error():
    """A non-repo path raises rather than returning an error string."""
    with pytest.raises(FlexLockSnapshotError):
        get_git_commit(path="/nonexistent/path")


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

# ── create_shadow_tree: write-tree only, no side effects (issue 3) ──


def _list_flexlock_refs(repo):
    refs_dir = Path(repo.git_dir) / "refs" / "flexlock"
    if not refs_dir.exists():
        return []
    return [p for p in refs_dir.rglob("*") if p.is_file()]


def test_create_shadow_tree_matches_shadow_snapshot(git_repo):
    """Same working tree -> same tree hash as create_shadow_snapshot."""
    repo_dir = Path(git_repo.working_dir)
    (repo_dir / "extra.txt").write_text("payload")

    snap = create_shadow_snapshot(repo_path=str(repo_dir))
    tree = create_shadow_tree(repo_path=str(repo_dir))

    assert tree["tree"] == snap["tree"]
    assert isinstance(tree["is_dirty"], bool)
    assert "commit" not in tree


def test_create_shadow_tree_creates_no_refs_or_commits(git_repo):
    """create_shadow_tree must not create refs/flexlock/runs/* or commits."""
    repo_dir = Path(git_repo.working_dir)
    (repo_dir / "extra.txt").write_text("payload")

    commits_before = sum(1 for _ in git_repo.iter_commits())
    refs_before = _list_flexlock_refs(git_repo)

    create_shadow_tree(repo_path=str(repo_dir))

    commits_after = sum(1 for _ in git_repo.iter_commits())
    refs_after = _list_flexlock_refs(git_repo)

    assert commits_after == commits_before
    assert refs_after == refs_before == []


def test_create_shadow_snapshot_does_create_a_ref(git_repo):
    """Contrast: the real snapshot path *does* persist a ref."""
    repo_dir = Path(git_repo.working_dir)
    create_shadow_snapshot(repo_path=str(repo_dir))
    assert _list_flexlock_refs(git_repo)  # non-empty


def test_create_shadow_tree_exclude_changes_scope(git_repo):
    """Excluding a file makes its content irrelevant to the tree hash."""
    repo_dir = Path(git_repo.working_dir)
    (repo_dir / "keep.txt").write_text("keep")
    (repo_dir / "junk.log").write_text("v1")

    t1 = create_shadow_tree(repo_path=str(repo_dir), exclude=["*.log"])["tree"]
    (repo_dir / "junk.log").write_text("v2-different")
    t2 = create_shadow_tree(repo_path=str(repo_dir), exclude=["*.log"])["tree"]

    assert t1 == t2  # excluded file change is invisible
