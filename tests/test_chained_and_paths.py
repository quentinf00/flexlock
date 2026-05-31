"""Tests for the bare-path Project loader fix (#28) and submit_chained (F)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from omegaconf import OmegaConf

from flexlock import Project
from flexlock.api import ChainedResult, ExecutionResult
from flexlock.utils import load_python_defaults


# --- load_python_defaults: bare path auto-detection ---

def _write_defaults_module(path: Path, var_name: str = "defaults", body: dict = None):
    body = body or {"train": {"lr": 0.01}}
    path.write_text(f"{var_name} = {body!r}\n")


def test_bare_py_path_auto_appends_defaults(tmp_path):
    """`configs/defaults.py` is treated as `configs/defaults.py:defaults`."""
    p = tmp_path / "defaults.py"
    _write_defaults_module(p)
    out = load_python_defaults(str(p))
    assert out == {"train": {"lr": 0.01}}


def test_explicit_colon_syntax_still_works(tmp_path):
    p = tmp_path / "myconfig.py"
    _write_defaults_module(p, var_name="my_anchors", body={"x": 1})
    out = load_python_defaults(f"{p}:my_anchors")
    assert out == {"x": 1}


def test_dotted_module_path_unchanged():
    """Regression: `pkg.module.var` still resolves as before."""
    # Use a stdlib module we know exists.
    out = load_python_defaults("pathlib.Path")
    assert out is Path


def test_slashed_nonexistent_path_gives_actionable_error(tmp_path):
    """`configs/missing.py` (doesn't exist) raises a clear hint."""
    from flexlock.exceptions import FlexLockConfigError

    with pytest.raises(FlexLockConfigError, match="path/to/file.py"):
        load_python_defaults("configs/does_not_exist.py")


def test_project_accepts_bare_py_path(tmp_path):
    """Project('configs/defaults.py') Just Works."""
    p = tmp_path / "defaults.py"
    _write_defaults_module(p, body={"stage": {"x": 1}})
    proj = Project(str(p))
    assert "stage" in proj.defaults
    assert proj.defaults.stage.x == 1


# --- submit_chained ---

def _make_proj_with_defaults():
    """Build a Project whose defaults include a stage that uses an anchor."""
    cfg = OmegaConf.create({
        "cnf_run_dir": "outputs/cnf_train/run_0001",
        "encode_val": {
            "data_dir": "${cnf_run_dir}/data",
            "save_dir": "outputs/encode/${cnf_run_dir}",
        },
        "cnf_eval_val": {
            "cnf_dir": "${cnf_run_dir}",
            "save_dir": "outputs/eval/${cnf_run_dir}",
        },
    })
    return Project(cfg)


def test_submit_chained_basic(tmp_path):
    """Sweep + 2 downstream stages, single anchor."""
    proj = _make_proj_with_defaults()

    # Base config for sweep
    base = OmegaConf.create({"save_dir": str(tmp_path / "cnf_sweep"), "x": 0})

    captured = []

    def fake_instantiate(c):
        captured.append(OmegaConf.to_container(c, resolve=True))
        return {}

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        chained = proj.submit_chained(
            base,
            sweep=[
                {"save_dir": str(tmp_path / "cnf_sweep" / "a")},
                {"save_dir": str(tmp_path / "cnf_sweep" / "b")},
            ],
            downstream=[
                ("encode_val", {"cnf_run_dir": "save_dir"}),
                ("cnf_eval_val", {"cnf_run_dir": "save_dir"}),
            ],
        )

    assert isinstance(chained, ChainedResult)
    assert len(chained.sweep) == 2
    assert len(chained.downstream) == 2
    assert len(chained.downstream[0]) == 2  # two downstream stages per parent

    # Each downstream stage should have seen the parent's save_dir as its anchor.
    # Total calls: 2 sweep items + 2*2 downstream = 6
    assert len(captured) == 6


def test_submit_chained_anchor_propagation(tmp_path):
    """The downstream stage's resolved data_dir reflects the parent's save_dir."""
    proj = _make_proj_with_defaults()
    base = OmegaConf.create({"save_dir": str(tmp_path / "cnf"), "x": 0})

    seen_data_dirs = []

    def fake_instantiate(c):
        # Capture only the encode_val/cnf_eval_val configs (they have data_dir / cnf_dir)
        d = OmegaConf.to_container(c, resolve=True)
        if "data_dir" in d:
            seen_data_dirs.append(d["data_dir"])
        return {}

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", side_effect=fake_instantiate):
        proj.submit_chained(
            base,
            sweep=[
                {"save_dir": str(tmp_path / "cnf" / "a")},
                {"save_dir": str(tmp_path / "cnf" / "b")},
            ],
            downstream=[("encode_val", {"cnf_run_dir": "save_dir"})],
        )

    # encode_val.data_dir = ${cnf_run_dir}/data → should reflect each parent's save_dir
    assert any(str(tmp_path / "cnf" / "a") in d for d in seen_data_dirs)
    assert any(str(tmp_path / "cnf" / "b") in d for d in seen_data_dirs)


def test_submit_chained_iteration_protocol(tmp_path):
    """ChainedResult yields (sweep_result, downstream_list) pairs."""
    proj = _make_proj_with_defaults()
    base = OmegaConf.create({"save_dir": str(tmp_path / "cnf"), "x": 0})

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={}):
        chained = proj.submit_chained(
            base,
            sweep=[{"save_dir": str(tmp_path / "cnf" / "a")}],
            downstream=[("encode_val", {"cnf_run_dir": "save_dir"})],
        )

    pairs = list(chained)
    assert len(pairs) == 1
    sweep_r, downstream_rs = pairs[0]
    assert isinstance(sweep_r, ExecutionResult)
    assert isinstance(downstream_rs, list)
    assert all(isinstance(r, ExecutionResult) for r in downstream_rs)


def test_submit_chained_requires_sweep_and_downstream(tmp_path):
    proj = _make_proj_with_defaults()
    base = OmegaConf.create({"save_dir": str(tmp_path / "x"), "x": 0})
    with pytest.raises(ValueError, match="submit_chained requires"):
        proj.submit_chained(base, sweep=[{}])
    with pytest.raises(ValueError, match="submit_chained requires"):
        proj.submit_chained(base, downstream=[("encode_val", {})])


def test_submit_chained_warns_on_missing_attr(tmp_path, caplog):
    """A wiring attr that doesn't exist on the result is logged, not crashed."""
    proj = _make_proj_with_defaults()
    base = OmegaConf.create({"save_dir": str(tmp_path / "x"), "x": 0})

    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={}):
        # Wiring references an attr the result doesn't have
        proj.submit_chained(
            base,
            sweep=[{"save_dir": str(tmp_path / "x" / "a")}],
            downstream=[("encode_val", {"cnf_run_dir": "totally_made_up_attr"})],
        )
    # No exception; just continues. (We don't assert on caplog because logger
    # is loguru, not stdlib; the visible signal is that no exception fires.)
