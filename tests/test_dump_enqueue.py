"""Tests for --dump, multi-file --sweep-file, and --enqueue.

Covers:
  - --dump: emits clean YAML (no headers), exits without running
  - --sweep-file FILE [FILE ...]: multiple files concatenated into one sweep
  - --enqueue FILE: appends compiled config to a YAML queue file
  - enqueue_to_file utility: create, append, type validation
  - end-to-end: enqueue several configs, run as a sweep
"""

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from omegaconf import OmegaConf

from flexlock import enqueue_to_file, load_sweep
from flexlock.runner import FlexLockRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_cfg(save_dir: str = "outputs/test", **extra) -> OmegaConf:
    return OmegaConf.create({"_target_": "builtins.dict", "save_dir": save_dir, **extra})


def _run(args: list[str]):
    """Run FlexLockRunner with the given args; return its return value."""
    runner = FlexLockRunner()
    return runner.run(cli_args=args)


# ---------------------------------------------------------------------------
# --dump
# ---------------------------------------------------------------------------

def test_dump_outputs_clean_yaml(tmp_path, capsys):
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.dump({"_target_": "builtins.dict", "save_dir": "out/run", "lr": 0.01}))

    result = _run(["--config", str(cfg_file), "--dump"])

    captured = capsys.readouterr().out
    parsed = yaml.safe_load(captured)
    assert isinstance(parsed, dict)
    assert parsed["lr"] == 0.01
    assert "=== COMPILED CONFIG ===" not in captured
    assert result is None


def test_dump_does_not_run(tmp_path, capsys):
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.dump({"_target_": "builtins.dict", "save_dir": str(tmp_path / "out")}))

    with patch("flexlock.api.instantiate") as mock_inst:
        _run(["--config", str(cfg_file), "--dump"])

    mock_inst.assert_not_called()


def test_dump_output_is_valid_sweep_item(tmp_path, capsys):
    """A --dump-captured file can be fed back as a --sweep-file item."""
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.dump({"_target_": "builtins.dict", "save_dir": "out/run", "x": 42}))

    _run(["--config", str(cfg_file), "--dump"])
    dump_yaml = capsys.readouterr().out

    dump_file = tmp_path / "captured.yaml"
    dump_file.write_text(dump_yaml)

    tasks = load_sweep(sweep_file=str(dump_file))
    assert len(tasks) == 1
    assert tasks[0]["x"] == 42


# ---------------------------------------------------------------------------
# multi-file --sweep-file
# ---------------------------------------------------------------------------

def test_load_sweep_multi_file_dicts(tmp_path):
    """Each file is a single dict → one task per file."""
    f1 = tmp_path / "a.yaml"
    f2 = tmp_path / "b.yaml"
    f1.write_text(yaml.dump({"lr": 0.001}))
    f2.write_text(yaml.dump({"lr": 0.01}))

    tasks = load_sweep(sweep_file=[str(f1), str(f2)])
    assert tasks == [{"lr": 0.001}, {"lr": 0.01}]


def test_load_sweep_multi_file_mixed(tmp_path):
    """One file is a list, one is a dict — results are concatenated."""
    f_list = tmp_path / "grid.yaml"
    f_single = tmp_path / "extra.yaml"
    f_list.write_text(yaml.dump([{"lr": 0.001}, {"lr": 0.01}]))
    f_single.write_text(yaml.dump({"lr": 0.1}))

    tasks = load_sweep(sweep_file=[str(f_list), str(f_single)])
    assert len(tasks) == 3
    assert tasks[-1] == {"lr": 0.1}


def test_load_sweep_single_file_still_works(tmp_path):
    """Passing a single path (string) keeps backward-compat behaviour."""
    f = tmp_path / "sweep.yaml"
    f.write_text(yaml.dump([{"lr": 0.001}, {"lr": 0.01}]))

    tasks = load_sweep(sweep_file=str(f))
    assert tasks == [{"lr": 0.001}, {"lr": 0.01}]


def test_load_sweep_file_not_found_raises(tmp_path):
    from flexlock.exceptions import FlexLockConfigError
    with pytest.raises(FlexLockConfigError, match="not found"):
        load_sweep(sweep_file=str(tmp_path / "nonexistent.yaml"))


def test_load_sweep_multi_file_one_missing_raises(tmp_path):
    from flexlock.exceptions import FlexLockConfigError
    good = tmp_path / "good.yaml"
    good.write_text(yaml.dump({"lr": 0.001}))
    with pytest.raises(FlexLockConfigError, match="not found"):
        load_sweep(sweep_file=[str(good), str(tmp_path / "missing.yaml")])


def test_sweep_file_cli_multi_runs_both(tmp_path):
    """--sweep-file FILE1 FILE2 on the CLI submits two tasks.

    Each file is an override dict (no save_dir); the base config provides
    the sweep root and _target_.
    """
    base_save = str(tmp_path / "sweep")
    base_file = tmp_path / "base.yaml"
    base_file.write_text(yaml.dump(
        {"_target_": "builtins.dict", "save_dir": base_save, "x": 0}
    ))

    f1 = tmp_path / "a.yaml"
    f2 = tmp_path / "b.yaml"
    f1.write_text(yaml.dump({"x": 1}))
    f2.write_text(yaml.dump({"x": 2}))

    captured_xs = []

    def fake_instantiate(cfg):
        captured_xs.append(OmegaConf.to_container(cfg, resolve=True).get("x"))
        return {}

    with patch("flexlock.api.snapshot"), \
         patch("flexlock.api.extract_tracking_info", return_value=({}, {}, None)), \
         patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        _run(["--config", str(base_file), "--sweep-file", str(f1), str(f2)])

    assert sorted(captured_xs) == [1, 2]


# ---------------------------------------------------------------------------
# enqueue_to_file utility
# ---------------------------------------------------------------------------

def test_enqueue_creates_file(tmp_path):
    q = tmp_path / "queue.yaml"
    n = enqueue_to_file(q, {"lr": 0.001})
    assert q.exists()
    assert n == 1
    data = yaml.safe_load(q.read_text())
    assert data == [{"lr": 0.001}]


def test_enqueue_appends(tmp_path):
    q = tmp_path / "queue.yaml"
    enqueue_to_file(q, {"lr": 0.001})
    n = enqueue_to_file(q, {"lr": 0.01})
    assert n == 2
    data = yaml.safe_load(q.read_text())
    assert len(data) == 2
    assert data[1]["lr"] == 0.01


def test_enqueue_creates_parent_dirs(tmp_path):
    q = tmp_path / "nested" / "deep" / "queue.yaml"
    enqueue_to_file(q, {"x": 1})
    assert q.exists()


def test_enqueue_wrong_type_raises(tmp_path):
    q = tmp_path / "bad.yaml"
    q.write_text("not_a_list: true\n")
    with pytest.raises(ValueError, match="must contain a YAML list"):
        enqueue_to_file(q, {"lr": 0.001})


# ---------------------------------------------------------------------------
# --enqueue CLI flag
# ---------------------------------------------------------------------------

def test_enqueue_cli_creates_queue(tmp_path):
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.dump({"_target_": "builtins.dict", "save_dir": "out", "lr": 0.001}))
    q = tmp_path / "queue.yaml"

    result = _run(["--config", str(cfg_file), "--enqueue", str(q)])

    assert result is None
    assert q.exists()
    data = yaml.safe_load(q.read_text())
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["lr"] == 0.001


def test_enqueue_cli_appends(tmp_path):
    q = tmp_path / "queue.yaml"
    base_cfg = {"_target_": "builtins.dict", "save_dir": "out"}

    for lr in (0.001, 0.01, 0.1):
        cfg_file = tmp_path / f"cfg_{lr}.yaml"
        cfg_file.write_text(yaml.dump({**base_cfg, "lr": lr}))
        _run(["--config", str(cfg_file), "--enqueue", str(q)])

    data = yaml.safe_load(q.read_text())
    assert len(data) == 3
    assert [d["lr"] for d in data] == [0.001, 0.01, 0.1]


def test_enqueue_cli_does_not_run(tmp_path):
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.dump({"_target_": "builtins.dict", "save_dir": "out"}))
    q = tmp_path / "queue.yaml"

    with patch("flexlock.api.instantiate") as mock_inst:
        _run(["--config", str(cfg_file), "--enqueue", str(q)])

    mock_inst.assert_not_called()


# ---------------------------------------------------------------------------
# End-to-end: enqueue → sweep-file
# ---------------------------------------------------------------------------

def test_enqueue_then_sweep_file(tmp_path):
    """Enqueue N override dicts, then run them via --sweep-file against a base config.

    Items in the queue are override dicts (lr only).  The base config
    provides _target_, save_dir, and the sweep root.
    """
    base_save = str(tmp_path / "sweep")
    base_file = tmp_path / "base.yaml"
    base_file.write_text(yaml.dump(
        {"_target_": "builtins.dict", "save_dir": base_save, "lr": 0.0}
    ))
    q = tmp_path / "queue.yaml"

    # Enqueue override dicts (not full configs)
    for lr in (0.001, 0.01):
        enqueue_to_file(q, {"lr": lr})

    captured_lrs = []

    def fake_instantiate(cfg):
        captured_lrs.append(OmegaConf.to_container(cfg, resolve=True).get("lr"))
        return {}

    with patch("flexlock.api.snapshot"), \
         patch("flexlock.api.extract_tracking_info", return_value=({}, {}, None)), \
         patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        _run(["--config", str(base_file), "--sweep-file", str(q)])

    assert sorted(captured_lrs) == [0.001, 0.01]
