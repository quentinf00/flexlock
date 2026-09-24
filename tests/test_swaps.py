"""Phase 4: `key=@name` swaps a subtree for a named config (replace, not merge)."""

import json
import sys

import pytest
from omegaconf import OmegaConf

from flexlock.api import Project
from flexlock.exceptions import FlexLockConfigError
from flexlock.record import load_record
from flexlock.runner import FlexLockRunner
from flexlock.utils import expand_swaps, merge_task_into_cfg

STAGE_SRC = """\
def run(save_dir, model=None, note=None):
    return {"model": model, "note": note}
"""

MODELS_SRC = """\
from flexlock import py2cfg

huge_model = py2cfg(dict, width=512, depth=8)
"""

XPS_SRC = """\
from flexlock import py2cfg
from swappkg.stage import run

small_model = py2cfg(dict, width=8, depth=2, dropout=0.1)
big_model = py2cfg(dict, width=64, depth=4)

train = dict(main=py2cfg(run, model=small_model, save_dir="RESULTS/train"))
"""


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    p = root / "swappkg"
    p.mkdir(parents=True)
    results = root / "results"
    (p / "__init__.py").write_text("")
    (p / "stage.py").write_text(STAGE_SRC)
    (p / "models.py").write_text(MODELS_SRC)
    (p / "xps.py").write_text(XPS_SRC.replace("RESULTS", str(results)))
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setenv("PYTHONPATH", str(root))
    monkeypatch.chdir(root)
    yield results
    for name in [m for m in sys.modules if m.startswith("swappkg")]:
        del sys.modules[name]


def _run(*argv):
    FlexLockRunner().run(["-d", "swappkg.xps.train", "-s", "main", *argv])


def _result(save_dir):
    return json.loads((save_dir / "results.json").read_text())


def test_swap_replaces_node(pkg):
    _run("-o", "main.model=@big_model")
    assert _result(pkg / "train")["model"] == {"width": 64, "depth": 4}  # no dropout


def test_later_override_applies_on_swapped_node(pkg):
    _run("-o", "main.model=@big_model", "main.model.width=16")
    assert _result(pkg / "train")["model"] == {"width": 16, "depth": 4}


def test_swap_after_select(pkg):
    _run("-O", "model=@big_model")
    assert _result(pkg / "train")["model"]["width"] == 64


def test_fully_qualified_swap(pkg):
    _run("-o", "main.model=@swappkg.models.huge_model")
    assert _result(pkg / "train")["model"] == {"width": 512, "depth": 8}


def test_double_at_is_literal(pkg):
    _run("-o", "main.note=@@home")
    assert _result(pkg / "train")["note"] == "@home"


def test_unknown_name_lists_config_attrs(pkg):
    with pytest.raises(FlexLockConfigError, match="big_model, small_model, train"):
        _run("-o", "main.model=@bigg_model")


def test_swap_recorded_as_typed_and_changes_fingerprint(pkg):
    _run("-o", "main.model=@big_model", "--save-dir-policy", "increment")
    _run("--save-dir-policy", "increment")
    big, small = (load_record(pkg / f"train_000{i}") for i in (0, 1))
    assert big["config"]["_preset_"]["overrides"] == ["main.model=@big_model"]
    assert big["config"]["model"]["width"] == 64
    assert big["fingerprint"] != small["fingerprint"]


def test_python_api_dict_overrides(pkg):
    res = Project("swappkg.xps.train").submit("main", overrides={"model": "@big_model"})
    assert res.result["model"] == {"width": 64, "depth": 4}


def test_sweep_values_swap(pkg):
    """--sweep "@a,@b" --sweep-target main.model: each item replaces the node."""
    module = sys.modules.get("swappkg.xps") or __import__("swappkg.xps").xps
    base = OmegaConf.create({"main": {"model": {"width": 8, "dropout": 0.1}}})
    item = expand_swaps("@big_model", module)
    merged = merge_task_into_cfg(base, item, "main.model")
    assert OmegaConf.to_container(merged.main.model) == {
        "_target_": "builtins.dict", "width": 64, "depth": 4,
    }


def test_sweep_file_swaps_end_to_end(pkg):
    sweep = pkg.parent / "sweep.yaml"
    sweep.write_text(
        f"- {{model: '@big_model', save_dir: {pkg}/sw/big}}\n"
        f"- {{model: '@small_model', save_dir: {pkg}/sw/small}}\n"
    )
    _run("--sweep-file", str(sweep), "--sweep-target", ".", "--n_jobs", "2")
    assert _result(pkg / "sw/big")["model"] == {"width": 64, "depth": 4}
    assert _result(pkg / "sw/small")["model"]["dropout"] == 0.1
