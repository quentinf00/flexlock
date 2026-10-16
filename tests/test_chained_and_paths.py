"""Tests for bare-path Project configuration loading."""

from pathlib import Path
from unittest.mock import patch

import pytest
from omegaconf import OmegaConf

from flexlock import Project
from flexlock.api import ExecutionResult
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


def test_file_based_target_is_reimportable(tmp_path):
    """py2cfg captured inside a file-loaded defaults module must produce a
    _target_ that can be re-imported (so submit() works, not just inspection).

    Before the fix the module was loaded under the literal name
    "dynamic_defaults", making `instantiate()` later fail with
    `ModuleNotFoundError: No module named 'dynamic_defaults'`.
    """
    import importlib
    import sys
    from flexlock.utils import instantiate

    cfg_file = tmp_path / "my_project_config.py"
    cfg_file.write_text(
        "from flexlock import py2cfg\n"
        "def train(lr=0.01):\n"
        "    return {'lr': lr}\n"
        "defaults = {'train': py2cfg(train)}\n"
    )

    # Make sure no stale entry pollutes the test
    sys.modules.pop("my_project_config", None)

    proj = Project(str(cfg_file))
    train_cfg = proj.get("train")
    # _target_ uses the file's stem and is importable
    assert train_cfg._target_ == "my_project_config.train"
    mod = importlib.import_module("my_project_config")
    assert hasattr(mod, "train")
    # End-to-end: instantiate dispatches to the real function
    result = instantiate(train_cfg)
    assert result == {"lr": 0.01}



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










    # No exception; just continues. (We don't assert on caplog because logger
    # is loguru, not stdlib; the visible signal is that no exception fires.)
