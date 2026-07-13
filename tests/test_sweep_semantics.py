"""Tests for sweep semantics (Spec C)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from omegaconf import OmegaConf

from flexlock import Project
from flexlock.exceptions import FlexLockValidationError


# --- Per-item save_dir containment ---

def test_sweep_save_dir_outside_root_raises_clearly(tmp_path):
    """Wiki: 'is not in the subpath of' opaque traceback.

    With validation, the user gets a clear error listing offending items.
    """
    proj = Project()
    sweep_root = tmp_path / "sweep"
    base = OmegaConf.create({"save_dir": str(sweep_root), "x": 0})

    with pytest.raises(FlexLockValidationError) as exc:
        proj.submit(
            base,
            sweep=[
                {"save_dir": str(sweep_root / "item_a"), "x": 1},
                {"save_dir": str(tmp_path / "outside_tree"), "x": 2},
            ],
            smart_run=False,
            n_jobs=1,
        )

    msg = str(exc.value)
    assert "save_dir" in msg
    assert "sweep root" in msg
    assert "item 1" in msg            # offender index named
    assert "outside_tree" in msg      # offender dir named
    assert "--sweep-root" in msg      # workaround hint


def test_sweep_save_dir_all_inside_root_runs(tmp_path):
    """Happy path: all per-item save_dirs nest under the sweep root."""
    proj = Project()
    sweep_root = tmp_path / "sweep"
    base = OmegaConf.create({"save_dir": str(sweep_root), "x": 0})

    captured = []

    def fake_instantiate(c):
        captured.append(OmegaConf.to_container(c, resolve=True))
        return {}

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        proj.submit(
            base,
            sweep=[
                {"save_dir": str(sweep_root / "a"), "x": 1},
                {"save_dir": str(sweep_root / "b"), "x": 2},
            ],
            smart_run=False,
            n_jobs=1,
        )

    assert len(captured) == 2
    assert sorted(c["x"] for c in captured) == [1, 2]


def test_sweep_root_overrides_validation(tmp_path):
    """--sweep-root lets items live outside the base config's save_dir."""
    proj = Project()
    base = OmegaConf.create({
        "_target_": "builtins.dict",
        "save_dir": str(tmp_path / "base"),
        "x": 0,
    })
    common_parent = tmp_path / "results"

    captured = []

    def fake_instantiate(c):
        captured.append(OmegaConf.to_container(c, resolve=True))
        return {}

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        proj.submit(
            base,
            sweep=[
                {"save_dir": str(common_parent / "exp_a"), "x": 1},
                {"save_dir": str(common_parent / "exp_b"), "x": 2},
            ],
            sweep_root=str(common_parent),
            smart_run=False,
            n_jobs=1,
        )

    assert sorted(c["x"] for c in captured) == [1, 2]


def test_sweep_validation_uses_first_item_parent_when_no_base_save_dir(tmp_path):
    """Without base.save_dir, sweep root is inferred from first item's parent."""
    proj = Project()
    common = tmp_path / "results"
    base = OmegaConf.create({"x": 0})

    with pytest.raises(FlexLockValidationError, match="sweep root"):
        proj.submit(
            base,
            sweep=[
                {"save_dir": str(common / "a"), "x": 1},
                {"save_dir": str(tmp_path / "elsewhere" / "b"), "x": 2},
            ],
            smart_run=False,
            n_jobs=1,
        )


# --- Worker resilience (marker fallback) ---

def test_marker_falls_back_to_absolute_when_db_outside_task_parent(tmp_path):
    """worker.py: marker stores absolute db path if relative_to fails."""
    # Simulate the marker-write logic directly. This is what worker.py does
    # at line ~75 after the resilience fix.
    db_path = tmp_path / "sweep_root" / "run.lock.tasks.db"
    db_path.parent.mkdir(parents=True)
    db_path.touch()

    task_save_dir = tmp_path / "elsewhere" / "run_0001"
    task_save_dir.mkdir(parents=True)

    db_abs = Path(db_path).resolve()
    try:
        db_str = str(db_abs.relative_to(task_save_dir.parent.resolve()))
    except ValueError:
        db_str = str(db_abs)

    assert db_str == str(db_abs)
    # No exception, fallback used.


def test_marker_uses_relative_path_when_within_tree(tmp_path):
    db_path = tmp_path / "sweep" / "run.lock.tasks.db"
    db_path.parent.mkdir(parents=True)
    db_path.touch()

    task_save_dir = tmp_path / "sweep" / "run_0001"
    task_save_dir.mkdir()

    db_abs = Path(db_path).resolve()
    db_str = str(db_abs.relative_to(task_save_dir.parent.resolve()))
    assert db_str == "run.lock.tasks.db"


# --- Intra-node refs track per-item save_dir overrides ---

def test_intra_node_save_dir_ref_tracks_sweep_override(tmp_path):
    """${save_dir}/logs inside the base config tracks per-item save_dir
    overrides — this is the recommended pattern.

    Cross-tree ${main.save_dir} refs are frozen at proj.get() time (Spec A)
    and won't track sweep overrides — see test below.
    """
    proj = Project()
    sweep_root = tmp_path / "sweep"
    base = OmegaConf.create({
        "save_dir": str(sweep_root),
        "log_dir": "${save_dir}/logs",
    })

    captured = []

    def fake_instantiate(c):
        captured.append(OmegaConf.to_container(c, resolve=True))
        return {}

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        proj.submit(
            base,
            sweep=[
                {"save_dir": str(sweep_root / "a")},
                {"save_dir": str(sweep_root / "b")},
            ],
            smart_run=False,
            n_jobs=1,
        )

    assert captured[0]["log_dir"] == str(sweep_root / "a" / "logs")
    assert captured[1]["log_dir"] == str(sweep_root / "b" / "logs")


def test_sweep_dir_suffix_nests_under_base_save_dir(tmp_path):
    """sweep_dir_suffix=True must produce children of the sweep root, not
    siblings — siblings always trip the containment validation.
    """
    proj = Project()
    sweep_root = tmp_path / "train"
    base = OmegaConf.create({"save_dir": str(sweep_root), "x": 0})

    captured = []

    def fake_instantiate(c):
        captured.append(OmegaConf.to_container(c, resolve=True))
        return {}

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        proj.submit(
            base,
            sweep=[{"x": 1}, {"x": 2}],
            sweep_dir_suffix=True,
            smart_run=False,
            n_jobs=1,
        )

    # Each item nests under sweep_root.
    save_dirs = [c["save_dir"] for c in captured]
    assert save_dirs == [
        str(sweep_root / "sweep_0000"),
        str(sweep_root / "sweep_0001"),
    ]


def test_cross_tree_ref_frozen_at_selection_then_static(tmp_path):
    """After Spec A, ${main.save_dir} refs are frozen at proj.get() time.

    A sweep that overrides save_dir won't re-resolve frozen cross-tree
    refs — they keep the value at selection time. Users should use intra-
    node refs like ${save_dir} instead. This test pins the contract.
    """
    from flexlock.utils import select_and_freeze_root_refs

    root = OmegaConf.create({
        "main": {"save_dir": str(tmp_path / "main")},
        "train": {
            "save_dir": str(tmp_path / "train"),
            "log_dir": "${main.save_dir}/logs",
        },
    })
    selected = select_and_freeze_root_refs(root, "train")
    raw = OmegaConf.to_container(selected, resolve=False)
    # ${main.save_dir} was frozen to a literal string at selection — not a
    # live ref anymore. Sweep overrides of save_dir won't change log_dir.
    assert raw["log_dir"] == f"{tmp_path}/main/logs"


# --- Sweep item injects a key referenced by a normal ${key} ref (Phase 3) ---

def test_sweep_item_key_referenced_by_normal_ref(tmp_path):
    """Merge-before-resolve lets a sweep-injected key be read by a *normal*
    ``${variable}`` ref — the migration target for the old ``${.variable}``
    relative-ref placeholder trick.

    The item is merged into the base first, so ``variable`` exists before any
    resolution and ``${variable}`` resolves cleanly per item.
    """
    proj = Project()
    scatter_root = tmp_path / "scatter"
    base = OmegaConf.create({
        "save_dir": scatter_root / "${variable}",
        "pred_variable": "${variable}",
    })

    captured = []

    def fake_instantiate(c):
        captured.append(OmegaConf.to_container(c, resolve=True))
        return {}

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        proj.submit(
            base,
            sweep=["hs", "phs0"],
            sweep_target="variable",
            smart_run=False,
            n_jobs=1,
        )

    assert captured[0]["pred_variable"] == "hs"
    assert captured[0]["save_dir"] == str(scatter_root / "hs")
    assert captured[1]["pred_variable"] == "phs0"
    assert captured[1]["save_dir"] == str(scatter_root / "phs0")


# --- print_config previews sweep items ---

def test_print_config_with_sweep_previews_each_item(tmp_path, capsys):
    proj = Project()
    base = OmegaConf.create({"save_dir": str(tmp_path / "out"), "lr": 0.1})

    result = proj.submit(
        base,
        sweep=[{"lr": 0.5}, {"lr": 0.9}],
        print_config=True,
    )

    assert result is None
    out = capsys.readouterr().out
    assert "sweep item 0" in out
    assert "sweep item 1" in out
    assert "0.5" in out
    assert "0.9" in out
