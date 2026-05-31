"""Tests for the expanded Project.submit signature (Spec B).

Covers: str-key dispatch, overrides, merge, sweep_target, print_config,
plus the load_sweep utility.
"""

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from omegaconf import OmegaConf

from flexlock import load_sweep, parse_sweep_string


# --- parse_sweep_string ---

def test_parse_sweep_string_primitives():
    assert parse_sweep_string("1,2,3") == [1, 2, 3]


def test_parse_sweep_string_keyvalue():
    assert parse_sweep_string("lr=0.1,lr=0.2") == [{"lr": 0.1}, {"lr": 0.2}]


def test_parse_sweep_string_quoted():
    assert parse_sweep_string('"a,b",c') == ["a,b", "c"]


# --- load_sweep ---

def test_load_sweep_from_string():
    assert load_sweep(sweep="1,2,3") == [1, 2, 3]


def test_load_sweep_from_list():
    items = [{"lr": 0.1}, {"lr": 0.01}]
    assert load_sweep(sweep=items) == items


def test_load_sweep_from_yaml_file(tmp_path):
    p = tmp_path / "sweep.yaml"
    p.write_text(yaml.safe_dump([{"lr": 0.1}, {"lr": 0.01}]))
    assert load_sweep(sweep_file=p) == [{"lr": 0.1}, {"lr": 0.01}]


def test_load_sweep_from_json_file(tmp_path):
    p = tmp_path / "sweep.json"
    p.write_text(json.dumps([{"lr": 0.1}, {"lr": 0.01}]))
    assert load_sweep(sweep_file=p) == [{"lr": 0.1}, {"lr": 0.01}]


def test_load_sweep_from_text_file(tmp_path):
    p = tmp_path / "sweep.txt"
    p.write_text("1\n2\n3\n")
    assert load_sweep(sweep_file=p) == [1, 2, 3]


def test_load_sweep_from_key():
    root = OmegaConf.create({"grid": [{"lr": 0.1}, {"lr": 0.01}]})
    assert load_sweep(sweep_key="grid", root_cfg=root) == [{"lr": 0.1}, {"lr": 0.01}]


def test_load_sweep_rejects_multiple_sources(tmp_path):
    from flexlock.exceptions import FlexLockValidationError

    with pytest.raises(FlexLockValidationError, match="only ONE"):
        load_sweep(sweep=[1], sweep_file=tmp_path / "x.yaml")


def test_load_sweep_none_returns_empty_list():
    assert load_sweep() == []


# --- Project.submit dispatch on str key ---

def test_submit_accepts_str_key(tmp_path):
    """proj.submit('key') resolves via proj.get and submits."""
    from flexlock.api import Project

    proj = Project.__new__(Project)
    proj.defaults_str = None
    proj.defaults = OmegaConf.create({
        "stage": {"save_dir": str(tmp_path / "out"), "x": 1}
    })

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={"ok": True}) as mock_inst:
        result = proj.submit("stage", smart_run=False)

    assert result.status == "SUCCESS"
    # The instantiate call should have received the resolved sub-node
    called_with = mock_inst.call_args[0][0]
    assert called_with.x == 1


# --- overrides + merge ---

def test_submit_applies_overrides_dict(tmp_path):
    from flexlock.api import Project

    proj = Project.__new__(Project)
    proj.defaults = OmegaConf.create({})

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "lr": 0.1})
    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={}) as mock_inst:
        proj.submit(cfg, overrides={"lr": 0.5}, smart_run=False)

    assert mock_inst.call_args[0][0].lr == 0.5


def test_submit_applies_overrides_dotlist(tmp_path):
    from flexlock.api import Project

    proj = Project.__new__(Project)
    proj.defaults = OmegaConf.create({})

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "a": {"b": 1}})
    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={}) as mock_inst:
        proj.submit(cfg, overrides=["a.b=99"], smart_run=False)

    assert mock_inst.call_args[0][0].a.b == 99


def test_submit_applies_merge_from_yaml(tmp_path):
    from flexlock.api import Project

    proj = Project.__new__(Project)
    proj.defaults = OmegaConf.create({})

    merge_path = tmp_path / "extra.yaml"
    merge_path.write_text(yaml.safe_dump({"lr": 0.9, "extra": "yes"}))

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "lr": 0.1})
    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={}) as mock_inst:
        proj.submit(cfg, merge=str(merge_path), smart_run=False)

    final = mock_inst.call_args[0][0]
    assert final.lr == 0.9
    assert final.extra == "yes"


def test_submit_merge_then_overrides_order(tmp_path):
    """overrides is applied AFTER merge — overrides wins."""
    from flexlock.api import Project

    proj = Project.__new__(Project)
    proj.defaults = OmegaConf.create({})

    merge_path = tmp_path / "m.yaml"
    merge_path.write_text(yaml.safe_dump({"lr": 0.5}))

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "lr": 0.1})
    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={}) as mock_inst:
        proj.submit(
            cfg, merge=str(merge_path), overrides={"lr": 0.99}, smart_run=False
        )

    assert mock_inst.call_args[0][0].lr == 0.99


# --- print_config ---

def test_submit_print_config_short_circuits(tmp_path, capsys):
    """print_config=True prints the resolved config and returns None without executing."""
    from flexlock.api import Project

    proj = Project.__new__(Project)
    proj.defaults = OmegaConf.create({})

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "lr": 0.1})
    with patch("flexlock.api.instantiate") as mock_inst:
        result = proj.submit(cfg, print_config=True)

    assert result is None
    mock_inst.assert_not_called()
    out = capsys.readouterr().out
    assert "lr:" in out
    assert "0.1" in out


# --- sweep_target ---

def test_submit_sweep_target_routes_items(tmp_path):
    """sweep_target places each item at the given dotted path."""
    from flexlock.api import Project

    proj = Project.__new__(Project)
    proj.defaults = OmegaConf.create({})

    save_dir = tmp_path / "sweep"
    cfg = OmegaConf.create({
        "save_dir": str(save_dir),
        "lit_module": {"lr": 0.1, "weight_decay": 0.0},
    })

    captured = []

    def fake_instantiate(c):
        # When called for a sweep item, the override should land under lit_module
        captured.append(OmegaConf.to_container(c, resolve=True))
        return {}

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        proj.submit(
            cfg,
            sweep=[{"lr": 0.5}, {"lr": 0.9}],
            sweep_target="lit_module",
            smart_run=False,
            n_jobs=1,
        )

    assert len(captured) == 2
    # Each captured config should have lit_module.lr overridden
    lrs = [c["lit_module"]["lr"] for c in captured]
    assert sorted(lrs) == [0.5, 0.9]


def test_submit_without_sweep_target_merges_at_root(tmp_path):
    """Default behavior: sweep items merge at root of base_config."""
    from flexlock.api import Project

    proj = Project.__new__(Project)
    proj.defaults = OmegaConf.create({})

    save_dir = tmp_path / "sweep"
    cfg = OmegaConf.create({"save_dir": str(save_dir), "lr": 0.1})

    captured = []

    def fake_instantiate(c):
        captured.append(OmegaConf.to_container(c, resolve=True))
        return {}

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        proj.submit(
            cfg,
            sweep=[{"lr": 0.5}, {"lr": 0.9}],
            smart_run=False,
            n_jobs=1,
        )

    assert len(captured) == 2
    lrs = [c["lr"] for c in captured]
    assert sorted(lrs) == [0.5, 0.9]
