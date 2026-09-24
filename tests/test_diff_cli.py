"""Tests for flexlock-diff: --format json + exit codes (Phase B)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from flexlock.diff_cli import main, run_comparison


def _write_lock(d, cfg):
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.lock").write_text(yaml.dump({"config": cfg}))
    return d


def test_run_comparison_match():
    is_match, diffs = run_comparison({"config": {"lr": 1}}, {"config": {"lr": 1}})
    assert is_match is True
    assert diffs == {}


def test_run_comparison_differ_reports_diffs():
    is_match, diffs = run_comparison({"config": {"lr": 1}}, {"config": {"lr": 2}})
    assert is_match is False
    assert "config" in diffs


def test_cli_exit_code_match(tmp_path):
    a = _write_lock(tmp_path / "a", {"lr": 0.1})
    b = _write_lock(tmp_path / "b", {"lr": 0.1})
    with patch("sys.argv", ["flexlock-diff", "dirs", str(a), str(b)]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0


def test_cli_exit_code_differ(tmp_path):
    a = _write_lock(tmp_path / "a", {"lr": 0.1})
    b = _write_lock(tmp_path / "b", {"lr": 0.2})
    with patch("sys.argv", ["flexlock-diff", "dirs", str(a), str(b)]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


def test_cli_exit_code_error_missing_dir(tmp_path):
    a = _write_lock(tmp_path / "a", {"lr": 0.1})
    with patch("sys.argv", ["flexlock-diff", "dirs", str(a), str(tmp_path / "nope")]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 2


def test_cli_json_output(tmp_path, capsys):
    a = _write_lock(tmp_path / "a", {"lr": 0.1})
    b = _write_lock(tmp_path / "b", {"lr": 0.2})
    with patch("sys.argv", ["flexlock-diff", "dirs", str(a), str(b), "--format", "json"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["match"] is False
    assert "config" in data["diffs"]


def test_run_comparison_reports_all_differing_sections():
    from flexlock.diff_cli import run_comparison

    a = {"config": {"lr": 1}, "data": {"x": "h1"}, "env": {"m/pixi.lock": "a"}}
    b = {"config": {"lr": 2}, "data": {"x": "h2"}, "env": {"m/pixi.lock": "b"}}
    is_match, diffs = run_comparison(a, b)
    assert not is_match
    assert {"config", "data", "env"} <= set(diffs)
