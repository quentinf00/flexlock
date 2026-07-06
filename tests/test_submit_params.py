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
    assert "=== COMPILED CONFIG ===" in out
    assert "lr:" in out
    assert "0.1" in out


def test_submit_print_config_shows_target_docstring(tmp_path, capsys):
    """When _target_ is set, print_config prints the docstring section too."""
    from flexlock.api import Project

    proj = Project.__new__(Project)
    proj.defaults = OmegaConf.create({})

    # Target a stdlib function we know has a docstring.
    cfg = OmegaConf.create({
        "_target_": "os.path.join",
        "save_dir": str(tmp_path / "out"),
    })
    proj.submit(cfg, print_config=True)
    out = capsys.readouterr().out
    assert "=== TARGET FUNCTION DOCSTRING ===" in out
    assert "Target: os.path.join" in out


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


# --- Module-level submit & Project(None) ---

def test_project_no_args_creates_empty_defaults():
    """Project() with no arguments works and has empty defaults."""
    from flexlock import Project

    proj = Project()
    assert proj.defaults is not None
    assert len(proj.defaults) == 0


def test_project_accepts_dictconfig_defaults():
    """Project(DictConfig) accepts a pre-built config directly."""
    from flexlock import Project

    cfg = OmegaConf.create({"stage": {"x": 1}})
    proj = Project(cfg)
    assert proj.defaults is cfg or proj.get("stage").x == 1


def test_module_level_submit(tmp_path):
    """flexlock.submit(cfg, **kw) goes through the full submit path."""
    import flexlock

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "x": 1})
    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={"ok": True}) as mock_inst:
        result = flexlock.submit(cfg, smart_run=False)

    assert result.status == "SUCCESS"
    assert mock_inst.call_args[0][0].x == 1


def test_project_submit_config_classmethod(tmp_path):
    """Project.submit_config classmethod is equivalent to Project().submit."""
    from flexlock import Project

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "x": 2})
    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={}) as mock_inst:
        Project.submit_config(cfg, smart_run=False)

    assert mock_inst.call_args[0][0].x == 2


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


# --- force reaches sweep items (issue 15) ---

def _counting_target(tick_file=None, x=0, save_dir=None):
    """Append a tick per execution so tests can count real (re-)runs."""
    with open(tick_file, "a") as f:
        f.write("1")
    return {"x": x}


def test_forced_sweep_reexecutes_all_items(tmp_path, monkeypatch):
    from flexlock.api import Project

    monkeypatch.setenv("FLEXLOCK_INDEX", str(tmp_path / "idx.db"))
    tick = tmp_path / "ticks.txt"
    base = tmp_path / "exp"
    cfg = OmegaConf.create(
        {
            "_target_": "tests.test_submit_params._counting_target",
            "tick_file": str(tick),
            "x": 0,
            "save_dir": str(base),
        }
    )
    sweep = [{"x": 1}, {"x": 2}]
    proj = Project()

    # First run: both items execute.
    proj.submit(
        cfg, sweep=sweep, n_jobs=1, sweep_dir_suffix=True, search_dirs=[str(base)]
    )
    assert len(tick.read_text()) == 2

    # Re-run without force: both cached, no new executions.
    proj.submit(
        cfg, sweep=sweep, n_jobs=1, sweep_dir_suffix=True, search_dirs=[str(base)]
    )
    assert len(tick.read_text()) == 2

    # Force: every item re-executes despite existing markers.
    proj.submit(
        cfg,
        sweep=sweep,
        n_jobs=1,
        sweep_dir_suffix=True,
        search_dirs=[str(base)],
        force=True,
    )
    assert len(tick.read_text()) == 4
