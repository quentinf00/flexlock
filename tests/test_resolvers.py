import pytest
from omegaconf import OmegaConf
from pathlib import Path
import time

from flexlock.resolvers import now_resolver, vinc_resolver
from flexlock import config


def test_now_resolver():
    """Test the now_resolver returns a string in the correct format."""
    # Test default format
    timestamp = now_resolver()
    assert isinstance(timestamp, str)
    try:
        time.strptime(timestamp, config.TIMESTAMP_FORMAT)
    except ValueError:
        pytest.fail("Default timestamp format is incorrect")

    # Test custom format
    timestamp_custom = now_resolver(fmt="%Y%m%d")
    assert isinstance(timestamp_custom, str)
    try:
        time.strptime(timestamp_custom, "%Y%m%d")
    except ValueError:
        pytest.fail("Custom timestamp format is incorrect")


def test_vinc_resolver(tmp_path):
    """Test the vinc_resolver correctly increments version numbers."""
    base_path = tmp_path / "experiment"

    # First call, should return experiment_0000
    path1 = vinc_resolver(str(base_path))
    assert path1 == str(tmp_path / "experiment_0000")
    Path(path1).mkdir()

    # Second call, should return experiment_0001
    path2 = vinc_resolver(str(base_path))
    assert path2 == str(tmp_path / "experiment_0001")
    Path(path2).mkdir()

    # Create a file with a higher version number manually
    (tmp_path / "experiment_0005").mkdir()

    # Next call should be experiment_0006
    path3 = vinc_resolver(str(base_path))
    assert path3 == str(tmp_path / "experiment_0006")


def test_vinc_resolver_with_custom_format(tmp_path):
    """Test vinc_resolver with a custom format string."""
    base_path = tmp_path / "run"
    fmt = "-v{i:02d}"

    # First call
    path1 = vinc_resolver(str(base_path), fmt=fmt)
    assert path1 == str(tmp_path / "run-v00")
    Path(path1).mkdir()

    # Second call
    path2 = vinc_resolver(str(base_path), fmt=fmt)
    assert path2 == str(tmp_path / "run-v01")


def test_latest_resolver(tmp_path):
    """Test the latest_resolver returns the most recently modified path."""
    from flexlock.resolvers import latest_resolver
    import time

    # Create test directories with different modification times
    dir1 = tmp_path / "results_0001"
    dir2 = tmp_path / "results_0002"
    dir3 = tmp_path / "results_0003"

    # Create in sequence to ensure different modification times
    dir1.mkdir()
    time.sleep(0.01)  # Small delay to ensure different timestamp
    dir2.mkdir()
    time.sleep(0.01)  # Small delay to ensure different timestamp
    dir3.mkdir()

    # Test with glob pattern
    pattern = str(tmp_path / "results_*")
    latest = latest_resolver(pattern)

    # Should return the most recently created/modified directory
    assert latest == str(dir3)


def test_latest_resolver_with_files(tmp_path):
    """Test the latest_resolver works with files too."""
    from flexlock.resolvers import latest_resolver
    import time

    # Create test files with different modification times
    file1 = tmp_path / "data_v1.txt"
    file2 = tmp_path / "data_v2.txt"
    file3 = tmp_path / "data_v3.txt"

    # Create files in sequence
    file1.write_text("content1")
    time.sleep(0.01)
    file2.write_text("content2")
    time.sleep(0.01)
    file3.write_text("content3")

    # Test with glob pattern
    pattern = str(tmp_path / "data_v*.txt")
    latest = latest_resolver(pattern)

    # Should return the most recently created/modified file
    assert latest == str(file3)


def test_latest_resolver_no_matches():
    """Test the latest_resolver returns the pattern when no matches are found."""
    from flexlock.resolvers import latest_resolver

    # Use a pattern that won't match anything
    pattern = "/nonexistent/directory/*.txt"
    result = latest_resolver(pattern)

    # Should return the original pattern when no matches
    assert result == pattern


def test_latest_resolver_with_globbing_patterns(tmp_path):
    """Test latest_resolver with different globbing patterns."""
    from flexlock.resolvers import latest_resolver
    import time

    # Create a nested directory structure
    subdir1 = tmp_path / "subdir1"
    subdir2 = tmp_path / "subdir2"
    subdir1.mkdir()
    subdir2.mkdir()

    # Create files in both subdirectories
    file1 = subdir1 / "file.txt"
    file2 = subdir2 / "file.txt"
    file1.write_text("content1")
    time.sleep(0.01)
    file2.write_text("content2")

    # Use recursive pattern
    pattern = str(tmp_path / "**" / "file.txt")
    latest = latest_resolver(pattern)

    # Should return the most recently created file
    assert latest == str(file2)


# ── run_lock resolver tests ────────────────────────────────────


def test_run_lock_resolver_basic(tmp_path):
    """Test reading a simple field from run.lock."""
    from flexlock.resolvers import run_lock_resolver
    import yaml

    run_dir = tmp_path / "train_0001"
    run_dir.mkdir()
    (run_dir / "run.lock").write_text(yaml.dump({
        "config": {
            "lr": 0.01,
            "save_dir": str(run_dir),
            "datamodule": {"stats_file": "/data/stats.json"},
        },
        "timestamp": "2026-03-18T10:00:00",
    }))

    assert run_lock_resolver(str(run_dir), "config.lr") == 0.01
    assert isinstance(run_lock_resolver(str(run_dir), "config.lr"), float)
    assert run_lock_resolver(str(run_dir), "config.datamodule.stats_file") == "/data/stats.json"
    assert run_lock_resolver(str(run_dir), "timestamp") == "2026-03-18T10:00:00"


def test_run_lock_resolver_nested(tmp_path):
    """Test reading deeply nested fields."""
    from flexlock.resolvers import run_lock_resolver
    import yaml

    run_dir = tmp_path / "flow_0001"
    run_dir.mkdir()
    (run_dir / "run.lock").write_text(yaml.dump({
        "config": {
            "lit_module": {
                "regression_checkpoint_path": "/models/reg.ckpt",
                "residual_stats_file": "/data/residual_stats.json",
            }
        }
    }))

    result = run_lock_resolver(str(run_dir), "config.lit_module.regression_checkpoint_path")
    assert result == "/models/reg.ckpt"


def test_run_lock_resolver_missing_key_with_default(tmp_path):
    """Test that missing key returns default when provided."""
    from flexlock.resolvers import run_lock_resolver
    import yaml

    run_dir = tmp_path / "run_0001"
    run_dir.mkdir()
    (run_dir / "run.lock").write_text(yaml.dump({"config": {"lr": 0.01}}))

    result = run_lock_resolver(str(run_dir), "config.nonexistent", "fallback")
    assert result == "fallback"


def test_run_lock_resolver_missing_key_no_default(tmp_path):
    """Test that missing key without default raises KeyError."""
    from flexlock.resolvers import run_lock_resolver
    import yaml

    run_dir = tmp_path / "run_0001"
    run_dir.mkdir()
    (run_dir / "run.lock").write_text(yaml.dump({"config": {"lr": 0.01}}))

    with pytest.raises(KeyError, match="not found"):
        run_lock_resolver(str(run_dir), "config.nonexistent")


def test_run_lock_resolver_missing_run_lock_with_default(tmp_path):
    """Test that missing run.lock returns default when provided."""
    from flexlock.resolvers import run_lock_resolver

    result = run_lock_resolver(str(tmp_path / "nonexistent"), "config.lr", "0.001")
    assert result == "0.001"


def test_run_lock_resolver_missing_run_lock_no_default(tmp_path):
    """Test that missing run.lock without default raises FileNotFoundError."""
    from flexlock.resolvers import run_lock_resolver

    with pytest.raises(FileNotFoundError, match="no run.lock found"):
        run_lock_resolver(str(tmp_path / "nonexistent"), "config.lr")


def test_run_lock_resolver_in_omegaconf(tmp_path):
    """Test the resolver works within OmegaConf interpolation."""
    import yaml

    # Register only run_lock if not already registered
    if not OmegaConf.has_resolver("run_lock"):
        from flexlock.resolvers import run_lock_resolver
        OmegaConf.register_new_resolver("run_lock", run_lock_resolver, use_cache=False)

    run_dir = tmp_path / "upstream_0001"
    run_dir.mkdir()
    (run_dir / "run.lock").write_text(yaml.dump({
        "config": {
            "datamodule": {"stats_file": "/data/norm_stats.json"},
            "_target_": "pkg.train",
        }
    }))

    cfg = OmegaConf.create({
        "run_dir": str(run_dir),
        "stats_file": "${run_lock:${run_dir},config.datamodule.stats_file}",
        "missing_field": "${run_lock:${run_dir},config.nonexistent,none}",
    })

    assert OmegaConf.to_container(cfg, resolve=True)["stats_file"] == "/data/norm_stats.json"
    assert OmegaConf.to_container(cfg, resolve=True)["missing_field"] == "none"


def test_run_lock_resolver_null_value(tmp_path):
    """Test that null values in run.lock return default or None."""
    from flexlock.resolvers import run_lock_resolver
    import yaml

    run_dir = tmp_path / "run_0001"
    run_dir.mkdir()
    (run_dir / "run.lock").write_text(yaml.dump({"config": {"optional_field": None}}))

    assert run_lock_resolver(str(run_dir), "config.optional_field", "fallback") == "fallback"
    assert run_lock_resolver(str(run_dir), "config.optional_field") is None


def test_vinc_stable_within_single_submit(tmp_path):
    """${vinc:} must resolve once per submit() so run.lock and run.complete
    land in the same dir.

    Without eager save_dir resolution the resolver fires once during snapshot
    (creates run_0000) and again when writing the complete marker (sees
    run_0000 exists, returns run_0001), splitting the two files.
    """
    from unittest.mock import patch
    from flexlock.api import Project

    base = tmp_path / "exp" / "run"
    cfg = OmegaConf.create({
        "save_dir": "${vinc:" + str(base) + "}",
        "x": 1,
    })
    proj = Project()
    with patch("flexlock.api.snapshot") as mock_snap, patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={"ok": True}):
        result = proj.submit(cfg, smart_run=False)

    # Both side-effects should target the same resolved dir.
    assert (Path(result.save_dir) / "run.complete").exists()
    assert Path(result.save_dir).name == "run_0000"
    # snapshot was called with the resolved string, not the ${vinc:} template
    snap_cfg = mock_snap.call_args[0][0]
    assert "${vinc" not in snap_cfg.save_dir


def test_vinc_advances_across_submits(tmp_path):
    """Independent submit() calls must each get a fresh vinc value."""
    from unittest.mock import patch
    from flexlock.api import Project

    base = tmp_path / "exp" / "run"
    saved = []

    def fake_snap(c, **kw):
        # Mimic what real snapshot does: create the resolved dir
        Path(c.save_dir).mkdir(parents=True, exist_ok=True)
        saved.append(c.save_dir)

    proj = Project()
    for _ in range(3):
        cfg = OmegaConf.create({
            "save_dir": "${vinc:" + str(base) + "}",
            "x": 1,
        })
        with patch("flexlock.api.snapshot", side_effect=fake_snap), patch(
            "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
        ), patch("flexlock.api.instantiate", return_value={"ok": True}):
            proj.submit(cfg, smart_run=False)

    # Each submit advances the counter; resolved dirs are unique.
    assert len(set(saved)) == 3
    assert [Path(s).name for s in saved] == ["run_0000", "run_0001", "run_0002"]


def test_vinc_stable_with_cross_tree_refs(tmp_path):
    """${main.save_dir} refs frozen as ${vinc:} by select_and_freeze_root_refs
    must not fire the resolver a second time after snapshot() creates the dir.

    Regression: select_and_freeze_root_refs substitutes cross-tree refs with the
    raw root value.  When save_dir=${vinc:...}, downstream refs (logger, dirpath)
    are also frozen as ${vinc:...} interpolation nodes.  instantiate() calls
    config.copy(), which creates a new OmegaConf instance with an empty resolver
    cache; if those nodes are not eagerly resolved before the copy, vinc: fires
    again after snapshot has created the directory and returns the next version.
    """
    from unittest.mock import patch
    from flexlock.api import Project
    from flexlock.utils import select_and_freeze_root_refs

    base = tmp_path / "exp" / "run"
    # Simulate the pattern from vae.py: save_dir is a vinc ref; logger and
    # dirpath reference save_dir via ${main.save_dir}.
    root_cfg = OmegaConf.create({
        "main": {
            "_target_": "builtins.dict",
            "save_dir": "${vinc:" + str(base) + "}",
            "logger_dir": "${main.save_dir}",
            "dirpath": "${main.save_dir}/checkpoints",
        }
    })

    # Simulate -s main: select the subtree (freezes ${main.save_dir} → ${vinc:...})
    node_cfg = select_and_freeze_root_refs(root_cfg, "main")

    captured = []

    def fake_snap(c, **kw):
        # Real snapshot creates the directory; mimic that so the next vinc: call
        # would advance the counter if the bug is present.
        Path(c.save_dir).mkdir(parents=True, exist_ok=True)
        captured.append(dict(save_dir=c.save_dir, logger_dir=c.logger_dir, dirpath=c.dirpath))

    proj = Project()
    with patch("flexlock.api.snapshot", side_effect=fake_snap), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={"ok": True}):
        result = proj.submit(node_cfg, smart_run=False)

    assert len(captured) == 1
    snap = captured[0]
    resolved_save = snap["save_dir"]
    # All three fields must resolve to the SAME version (not _0000 vs _0001)
    assert snap["logger_dir"] == resolved_save
    assert snap["dirpath"] == resolved_save + "/checkpoints"
    assert Path(resolved_save).name == "run_0000"


def test_run_lock_resolver_native_types(tmp_path):
    """Test that native YAML types are preserved: int, float, bool, list."""
    from flexlock.resolvers import run_lock_resolver
    import yaml

    run_dir = tmp_path / "run_0001"
    run_dir.mkdir()
    (run_dir / "run.lock").write_text(yaml.dump({
        "config": {
            "epochs": 150,
            "lr": 3e-4,
            "use_amp": True,
            "hidden_dims": [128, 256, 128],
        }
    }))

    assert run_lock_resolver(str(run_dir), "config.epochs") == 150
    assert isinstance(run_lock_resolver(str(run_dir), "config.epochs"), int)
    assert run_lock_resolver(str(run_dir), "config.lr") == 3e-4
    assert isinstance(run_lock_resolver(str(run_dir), "config.lr"), float)
    assert run_lock_resolver(str(run_dir), "config.use_amp") is True
    assert run_lock_resolver(str(run_dir), "config.hidden_dims") == [128, 256, 128]
