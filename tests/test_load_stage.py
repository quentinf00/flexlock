"""Tests for load_stage module — lineage/prevs backwards compatibility."""

import pytest
import yaml
from pathlib import Path

from flexlock.load_stage import load_stage_from_path, _load_and_flatten_recursively


@pytest.fixture
def run_tree(tmp_path):
    """Create a tree of run directories with run.lock files for testing lineage."""

    def _make_run(name, config, lineage=None, lineage_key="lineage"):
        run_dir = tmp_path / name
        run_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": "2026-01-01T00:00:00",
            "config": config,
        }
        if lineage:
            data[lineage_key] = lineage
        (run_dir / "run.lock").write_text(yaml.dump(data))
        return str(run_dir)

    return _make_run


def test_load_stage_basic(run_tree):
    """Test loading a single stage with no lineage."""
    path = run_tree("run_001", {"lr": 0.01, "save_dir": "run_001"})
    result = load_stage_from_path(path)
    assert "run_001" in result
    assert result["run_001"]["config"]["lr"] == 0.01


def test_load_stage_with_lineage_field(run_tree):
    """Test loading stages linked via the new 'lineage' field."""
    upstream = run_tree("upstream", {"lr": 0.01, "save_dir": "upstream"})
    downstream = run_tree(
        "downstream",
        {"lr": 0.1, "save_dir": "downstream"},
        lineage={"upstream": {"path": upstream}},
        lineage_key="lineage",
    )

    result = load_stage_from_path(downstream)
    assert "downstream" in result
    assert "upstream" in result
    assert result["upstream"]["config"]["lr"] == 0.01


def test_load_stage_with_prevs_field(run_tree):
    """Test loading stages linked via the legacy 'prevs' field."""
    upstream = run_tree("upstream_legacy", {"lr": 0.01, "save_dir": "upstream_legacy"})
    downstream = run_tree(
        "downstream_legacy",
        {"lr": 0.1, "save_dir": "downstream_legacy"},
        lineage={
            "upstream_legacy": {"config": {"save_dir": upstream}}
        },
        lineage_key="prevs",
    )

    result = load_stage_from_path(downstream)
    assert "downstream_legacy" in result
    assert "upstream_legacy" in result


def test_load_stage_lineage_preferred_over_prevs(run_tree, tmp_path):
    """Test that 'lineage' takes priority when both fields are present."""
    upstream_new = run_tree("upstream_new", {"lr": 0.001, "save_dir": "upstream_new"})
    upstream_old = run_tree("upstream_old", {"lr": 0.999, "save_dir": "upstream_old"})

    # Manually create run.lock with both fields
    mixed_dir = tmp_path / "mixed"
    mixed_dir.mkdir()
    data = {
        "timestamp": "2026-01-01T00:00:00",
        "config": {"save_dir": "mixed"},
        "lineage": {"upstream_new": {"path": upstream_new}},
        "prevs": {"upstream_old": {"config": {"save_dir": upstream_old}}},
    }
    (mixed_dir / "run.lock").write_text(yaml.dump(data))

    result = load_stage_from_path(str(mixed_dir))
    # Should follow lineage (new) not prevs (legacy)
    assert "upstream_new" in result
    assert "upstream_old" not in result


def test_load_stage_deep_lineage(run_tree):
    """Test recursive lineage loading (grandparent chain)."""
    grandparent = run_tree("grandparent", {"step": 1, "save_dir": "grandparent"})
    parent = run_tree(
        "parent",
        {"step": 2, "save_dir": "parent"},
        lineage={"grandparent": {"path": grandparent}},
    )
    child = run_tree(
        "child",
        {"step": 3, "save_dir": "child"},
        lineage={"parent": {"path": parent}},
    )

    result = load_stage_from_path(child)
    assert len(result) == 3
    assert "grandparent" in result
    assert "parent" in result
    assert "child" in result


def test_load_stage_deduplicates(run_tree):
    """Test that shared ancestors are not loaded twice."""
    shared = run_tree("shared", {"role": "shared", "save_dir": "shared"})
    branch_a = run_tree(
        "branch_a",
        {"role": "a", "save_dir": "branch_a"},
        lineage={"shared": {"path": shared}},
    )
    branch_b = run_tree(
        "branch_b",
        {"role": "b", "save_dir": "branch_b"},
        lineage={"shared": {"path": shared}},
    )

    # Manually create a merge node
    merge_dir = run_tree(
        "merge",
        {"role": "merge", "save_dir": "merge"},
        lineage={
            "branch_a": {"path": branch_a},
            "branch_b": {"path": branch_b},
        },
    )

    result = load_stage_from_path(merge_dir)
    assert len(result) == 4  # shared, branch_a, branch_b, merge


def test_load_stage_missing_lock(tmp_path):
    """Test error when run.lock is missing."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="run.lock not found"):
        load_stage_from_path(str(empty_dir))


def test_load_stage_missing_path_in_lineage(run_tree, tmp_path):
    """Test error when lineage entry has no path."""
    bad_dir = tmp_path / "bad_lineage"
    bad_dir.mkdir()
    data = {
        "timestamp": "2026-01-01T00:00:00",
        "config": {"save_dir": "bad"},
        "lineage": {"broken": {}},  # no path, no config.save_dir
    }
    (bad_dir / "run.lock").write_text(yaml.dump(data))

    with pytest.raises(ValueError, match="Could not find path"):
        load_stage_from_path(str(bad_dir))


def test_lineage_stripped_from_output(run_tree):
    """Test that lineage/prevs fields are removed from returned stage data."""
    upstream = run_tree("up", {"save_dir": "up"})
    downstream = run_tree(
        "down",
        {"save_dir": "down"},
        lineage={"up": {"path": upstream}},
    )

    result = load_stage_from_path(downstream)
    for stage_data in result.values():
        assert "lineage" not in stage_data
        assert "prevs" not in stage_data
