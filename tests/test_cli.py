"""Tests for the unified flexlock CLI (ls, tag, gc)."""

import pytest
import yaml
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from git import Repo

from flexlock.cli import (
    find_results_dirs,
    get_flexlock_tags,
    get_tag_details,
    collect_lineage_refs,
    cmd_ls,
    cmd_tag,
    cmd_gc,
    main,
)
from flexlock.git_utils import sanitize_ref_name


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with an initial commit."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = Repo.init(repo_dir)
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()

    readme = repo_dir / "README.md"
    readme.write_text("init")
    repo.index.add([str(readme)])
    repo.index.commit("Initial commit")

    return repo


@pytest.fixture
def results_tree(tmp_path):
    """Create a results directory structure with run.lock files."""

    def _make_run(name, config=None, lineage=None, timestamp="2026-03-15T10:00:00"):
        run_dir = tmp_path / "results" / name
        run_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": timestamp,
            "config": config or {"_target_": "mod.func", "save_dir": str(run_dir)},
        }
        if lineage:
            data["lineage"] = lineage
        (run_dir / "run.lock").write_text(yaml.dump(data))
        return str(run_dir)

    return _make_run


def _make_args(**kwargs):
    """Create a simple namespace to mimic argparse output."""
    from argparse import Namespace

    defaults = {
        "path": None,
        "verbose": False,
        "format": "table",
        "name": None,
        "message": None,
        "list": False,
        "delete": None,
        "dry_run": False,
        "force": False,
        "refs": False,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


# ── find_results_dirs ──────────────────────────────────────────


def test_find_results_dirs_empty(tmp_path):
    """Test with a directory that has no runs."""
    assert find_results_dirs(str(tmp_path)) == []


def test_find_results_dirs_finds_runs(results_tree, tmp_path):
    """Test that runs are discovered and sorted by timestamp."""
    results_tree("run_a", timestamp="2026-03-15T08:00:00")
    results_tree("run_b", timestamp="2026-03-15T12:00:00")
    results_tree("run_c", timestamp="2026-03-15T10:00:00")

    runs = find_results_dirs(str(tmp_path / "results"))
    assert len(runs) == 3
    # Should be sorted descending by timestamp
    timestamps = [r["timestamp"] for r in runs]
    assert timestamps == sorted(timestamps, reverse=True)


def test_find_results_dirs_reads_config(results_tree, tmp_path):
    """Test that config data is read from run.lock."""
    results_tree("run_x", config={"_target_": "my.func", "lr": 0.01})
    runs = find_results_dirs(str(tmp_path / "results"))
    assert runs[0]["config"]["_target_"] == "my.func"
    assert runs[0]["config"]["lr"] == 0.01


def test_find_results_dirs_reads_lineage(results_tree, tmp_path):
    """Test that lineage data is read from run.lock."""
    results_tree(
        "run_with_lineage",
        lineage={"prev_stage": {"path": "/some/path"}},
    )
    runs = find_results_dirs(str(tmp_path / "results"))
    assert "prev_stage" in runs[0]["lineage"]


# ── cmd_ls ─────────────────────────────────────────────────────


def test_cmd_ls_no_runs(tmp_path, capsys):
    """Test ls with no results."""
    args = _make_args(path=str(tmp_path))
    cmd_ls(args)
    out = capsys.readouterr().out
    assert "No runs found" in out


def test_cmd_ls_table_output(results_tree, tmp_path, capsys):
    """Test ls with table output."""
    results_tree("stage_a", timestamp="2026-03-15T14:30:00")
    args = _make_args(path=str(tmp_path / "results"))
    cmd_ls(args)
    out = capsys.readouterr().out
    assert "stage_a" in out
    assert "2026-03-15 14:30" in out


def test_cmd_ls_json_output(results_tree, tmp_path, capsys):
    """Test ls with JSON output."""
    results_tree("stage_json")
    args = _make_args(path=str(tmp_path / "results"), format="json")
    cmd_ls(args)
    out = capsys.readouterr().out
    import json
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) == 1


def test_cmd_ls_verbose(results_tree, tmp_path, capsys):
    """Test ls verbose shows target and lineage."""
    results_tree(
        "verbose_run",
        config={"_target_": "pkg.train", "save_dir": "x"},
        lineage={"prev": {"path": "/prev"}},
    )
    args = _make_args(path=str(tmp_path / "results"), verbose=True)
    cmd_ls(args)
    out = capsys.readouterr().out
    assert "pkg.train" in out
    assert "prev" in out


# ── tag operations ─────────────────────────────────────────────


def test_tag_create(git_repo, tmp_path, capsys):
    """Test creating a tag for a run."""
    # Create a run inside the git repo
    run_dir = Path(git_repo.working_dir) / "results" / "my_run"
    run_dir.mkdir(parents=True)
    (run_dir / "run.lock").write_text(yaml.dump({
        "timestamp": "2026-03-15T10:00:00",
        "config": {"save_dir": str(run_dir)},
    }))

    args = _make_args(name="baseline_v1", path=str(run_dir))
    cmd_tag(args)

    out = capsys.readouterr().out
    assert "Tagged 'baseline_v1'" in out

    # Verify the ref was created
    tags = get_flexlock_tags(git_repo)
    assert "baseline_v1" in tags


def test_tag_list(git_repo, capsys):
    """Test listing tags."""
    # Create a tag ref manually
    tree_hash = git_repo.head.commit.tree.hexsha
    parent = git_repo.head.commit.hexsha
    msg = "FlexLock Tag: test_tag\nPath: /some/path\nTagged: 2026-03-15T10:00:00\n"
    commit = git_repo.git.commit_tree(tree_hash, "-p", parent, "-m", msg)
    git_repo.git.update_ref("refs/flexlock/tags/test_tag", commit)

    args = _make_args(list=True, verbose=False)
    with patch("flexlock.cli.find_git_repo", return_value=git_repo):
        cmd_tag(args)

    out = capsys.readouterr().out
    assert "test_tag" in out


def test_tag_delete(git_repo, capsys):
    """Test deleting a tag."""
    # Create tag
    tree_hash = git_repo.head.commit.tree.hexsha
    parent = git_repo.head.commit.hexsha
    msg = "FlexLock Tag: to_delete\nPath: /x\n"
    commit = git_repo.git.commit_tree(tree_hash, "-p", parent, "-m", msg)
    git_repo.git.update_ref("refs/flexlock/tags/to_delete", commit)

    assert "to_delete" in get_flexlock_tags(git_repo)

    args = _make_args(delete="to_delete")
    with patch("flexlock.cli.find_git_repo", return_value=git_repo):
        cmd_tag(args)

    out = capsys.readouterr().out
    assert "Deleted tag 'to_delete'" in out
    assert "to_delete" not in get_flexlock_tags(git_repo)


def test_tag_with_message(git_repo, capsys):
    """Test creating a tag with a custom message."""
    run_dir = Path(git_repo.working_dir) / "results" / "msg_run"
    run_dir.mkdir(parents=True)
    (run_dir / "run.lock").write_text(yaml.dump({
        "timestamp": "2026-03-15T10:00:00",
        "config": {"save_dir": str(run_dir)},
    }))

    args = _make_args(name="annotated", path=str(run_dir), message="Best run so far")
    cmd_tag(args)

    tags = get_flexlock_tags(git_repo)
    details = get_tag_details(git_repo, tags["annotated"])
    assert "Best run so far" in details["message"]


def test_tag_links_lineage_parents(git_repo, capsys):
    """Test that tagging a run links to lineage shadow commits."""
    repo_dir = Path(git_repo.working_dir)

    # Create upstream run with a shadow commit recorded in repos
    upstream_dir = repo_dir / "results" / "upstream"
    upstream_dir.mkdir(parents=True)

    # Create a shadow commit to reference
    tree_hash = git_repo.head.commit.tree.hexsha
    parent_hash = git_repo.head.commit.hexsha
    shadow_commit = git_repo.git.commit_tree(
        tree_hash, "-p", parent_hash, "-m", "FlexLock Shadow: upstream"
    )
    git_repo.git.update_ref(
        f"refs/flexlock/runs/upstream_shadow_abc",
        shadow_commit,
    )

    (upstream_dir / "run.lock").write_text(yaml.dump({
        "timestamp": "2026-03-15T09:00:00",
        "config": {"save_dir": str(upstream_dir)},
        "repos": {"main": {"commit": shadow_commit, "tree": tree_hash}},
    }))

    # Create downstream run referencing upstream
    downstream_dir = repo_dir / "results" / "downstream"
    downstream_dir.mkdir(parents=True)
    (downstream_dir / "run.lock").write_text(yaml.dump({
        "timestamp": "2026-03-15T10:00:00",
        "config": {"save_dir": str(downstream_dir)},
        "lineage": {"upstream": {"path": str(upstream_dir)}},
    }))

    args = _make_args(name="full_pipeline", path=str(downstream_dir))
    cmd_tag(args)

    tags = get_flexlock_tags(git_repo)
    details = get_tag_details(git_repo, tags["full_pipeline"])
    # Should have at least the upstream shadow commit as parent
    assert len(details["parents"]) >= 1


# ── gc operations ──────────────────────────────────────────────


def test_gc_dry_run(git_repo, capsys):
    """Test gc dry run shows what would be deleted."""
    repo_dir = Path(git_repo.working_dir)

    # Create untagged runs
    for name in ["run_a", "run_b"]:
        run_dir = repo_dir / "results" / name
        run_dir.mkdir(parents=True)
        (run_dir / "run.lock").write_text(yaml.dump({
            "timestamp": "2026-03-15T10:00:00",
            "config": {"save_dir": str(run_dir)},
        }))

    args = _make_args(path=str(repo_dir / "results"), dry_run=True)
    cmd_gc(args)

    out = capsys.readouterr().out
    assert "2 untagged run(s)" in out
    assert "dry run" in out
    # Files should still exist
    assert (repo_dir / "results" / "run_a" / "run.lock").exists()


def test_gc_deletes_untagged(git_repo, capsys):
    """Test gc deletes untagged runs when forced."""
    repo_dir = Path(git_repo.working_dir)

    # Create an untagged run
    untagged = repo_dir / "results" / "untagged"
    untagged.mkdir(parents=True)
    (untagged / "run.lock").write_text(yaml.dump({
        "timestamp": "2026-03-15T10:00:00",
        "config": {"save_dir": str(untagged)},
    }))

    # Create a tagged run
    tagged = repo_dir / "results" / "tagged"
    tagged.mkdir(parents=True)
    (tagged / "run.lock").write_text(yaml.dump({
        "timestamp": "2026-03-15T11:00:00",
        "config": {"save_dir": str(tagged)},
    }))

    # Tag the second run
    tree_hash = git_repo.head.commit.tree.hexsha
    parent_hash = git_repo.head.commit.hexsha
    msg = f"FlexLock Tag: keeper\nPath: {tagged.resolve()}\n"
    commit = git_repo.git.commit_tree(tree_hash, "-p", parent_hash, "-m", msg)
    git_repo.git.update_ref("refs/flexlock/tags/keeper", commit)

    args = _make_args(path=str(repo_dir / "results"), force=True)
    cmd_gc(args)

    out = capsys.readouterr().out
    assert "Deleted 1 run" in out
    assert not untagged.exists()
    assert tagged.exists()


def test_gc_protects_lineage(git_repo, capsys):
    """Test gc preserves lineage dependencies of tagged runs."""
    repo_dir = Path(git_repo.working_dir)

    # upstream (not tagged, but is lineage of a tagged run)
    upstream = repo_dir / "results" / "upstream"
    upstream.mkdir(parents=True)
    (upstream / "run.lock").write_text(yaml.dump({
        "timestamp": "2026-03-15T09:00:00",
        "config": {"save_dir": str(upstream)},
    }))

    # downstream (tagged)
    downstream = repo_dir / "results" / "downstream"
    downstream.mkdir(parents=True)
    (downstream / "run.lock").write_text(yaml.dump({
        "timestamp": "2026-03-15T10:00:00",
        "config": {"save_dir": str(downstream)},
        "lineage": {"upstream": {"path": str(upstream)}},
    }))

    # Tag downstream
    tree_hash = git_repo.head.commit.tree.hexsha
    msg = f"FlexLock Tag: pipeline\nPath: {downstream.resolve()}\n"
    commit = git_repo.git.commit_tree(
        tree_hash, "-p", git_repo.head.commit.hexsha, "-m", msg
    )
    git_repo.git.update_ref("refs/flexlock/tags/pipeline", commit)

    args = _make_args(path=str(repo_dir / "results"), force=True)
    cmd_gc(args)

    out = capsys.readouterr().out
    # Both should be kept — downstream is tagged, upstream is lineage
    assert "Nothing to clean up" in out
    assert upstream.exists()
    assert downstream.exists()


def test_gc_no_runs(tmp_path, capsys):
    """Test gc with empty directory."""
    args = _make_args(path=str(tmp_path))
    cmd_gc(args)
    out = capsys.readouterr().out
    assert "No runs found" in out


# ── get_flexlock_tags ──────────────────────────────────────────


def test_get_flexlock_tags_empty(git_repo):
    """Test that empty repo returns no tags."""
    assert get_flexlock_tags(git_repo) == {}


def test_get_flexlock_tags_returns_tags(git_repo):
    """Test that created tags are returned."""
    tree_hash = git_repo.head.commit.tree.hexsha
    parent = git_repo.head.commit.hexsha

    for name in ["alpha", "beta"]:
        msg = f"FlexLock Tag: {name}\nPath: /x/{name}\n"
        commit = git_repo.git.commit_tree(tree_hash, "-p", parent, "-m", msg)
        git_repo.git.update_ref(f"refs/flexlock/tags/{name}", commit)

    tags = get_flexlock_tags(git_repo)
    assert "alpha" in tags
    assert "beta" in tags
    assert len(tags) == 2


# ── get_tag_details ────────────────────────────────────────────


def test_get_tag_details_message_and_parents(git_repo):
    """Test tag details include message and parent commits."""
    tree_hash = git_repo.head.commit.tree.hexsha
    parent = git_repo.head.commit.hexsha

    msg = "FlexLock Tag: detail_test\nPath: /test\n"
    commit = git_repo.git.commit_tree(tree_hash, "-p", parent, "-m", msg)
    git_repo.git.update_ref("refs/flexlock/tags/detail_test", commit)

    details = get_tag_details(git_repo, commit)
    assert "detail_test" in details["message"]
    assert parent in details["parents"]
    assert details["timestamp"] != ""


# ── collect_lineage_refs ───────────────────────────────────────


def test_collect_lineage_refs_from_repos(git_repo):
    """Test collecting shadow commit refs from run.lock repos data."""
    repo_dir = Path(git_repo.working_dir)
    run_dir = repo_dir / "results" / "collect_test"
    run_dir.mkdir(parents=True)

    shadow_hash = git_repo.head.commit.hexsha  # use HEAD as a stand-in
    (run_dir / "run.lock").write_text(yaml.dump({
        "timestamp": "2026-01-01T00:00:00",
        "config": {"save_dir": str(run_dir)},
        "repos": {"main": {"commit": shadow_hash, "tree": "abc123"}},
    }))

    refs = collect_lineage_refs(git_repo, str(run_dir))
    assert shadow_hash in refs


# ── sanitize_ref_name ──────────────────────────────────────────


def test_sanitize_ref_name_spaces():
    assert " " not in sanitize_ref_name("my tag name")


def test_sanitize_ref_name_special_chars():
    result = sanitize_ref_name("tag~1^2:3?4*5[6")
    for char in ["~", "^", ":", "?", "*", "["]:
        assert char not in result


# ── main entry point ───────────────────────────────────────────


def test_main_no_command(capsys):
    """Test main with no arguments prints help and exits."""
    with pytest.raises(SystemExit):
        with patch("sys.argv", ["flexlock"]):
            main()


def test_main_ls(tmp_path, capsys):
    """Test main dispatches to ls subcommand."""
    with patch("sys.argv", ["flexlock", "ls", str(tmp_path)]):
        main()
    out = capsys.readouterr().out
    assert "No runs found" in out
