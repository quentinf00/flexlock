"""Phase 2: presets recorded on runs, preset links, `flexlock runs/presets`."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from git import Repo
from omegaconf import OmegaConf

from flexlock.api import Project
from flexlock.fingerprint import fingerprint
from flexlock.presets import (
    PRESET_KEY,
    address_matches,
    canonical_defaults,
    find_runs,
    list_presets,
    make_preset,
    presets_roots,
)
from flexlock.record import load_record
from flexlock.runner import FlexLockRunner
from flexlock.utils import instantiate

STAGE_SRC = "def run(save_dir, x=1, model=None, log=None):\n    return {'x': x}\n"

XPS_SRC = '''\
from flexlock import py2cfg
from prespkg.stage import run

# A building block: no save_dir, so not a preset.
small_model = py2cfg(dict, width=8)

# Baseline training run.
# Second line of the comment.
train_a = dict(main=py2cfg(run, x=1, model=small_model,
                           save_dir="${results}/train_a"),
               results="RESULTS")

# ============
# Pipeline with two stages.
pipe = dict(
    prep=py2cfg(run, x=2, save_dir="RESULTS/pipe/prep"),
    train=py2cfg(run, x=3, save_dir="RESULTS/pipe/train"),
)

_private = dict(main=py2cfg(run, save_dir="RESULTS/private"))
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A git project with a stage package, a config module and a .flexlock/."""
    root = tmp_path / "proj"
    pkg = root / "prespkg"
    pkg.mkdir(parents=True)
    results = root / "results"
    (pkg / "__init__.py").write_text("")
    (pkg / "stage.py").write_text(STAGE_SRC)
    (pkg / "xps.py").write_text(XPS_SRC.replace("RESULTS", str(results)))
    repo = Repo.init(root)
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["prespkg/__init__.py", "prespkg/stage.py", "prespkg/xps.py"])
    repo.index.commit("init")
    (root / ".flexlock").mkdir()  # project-level index + preset links
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setenv("PYTHONPATH", str(root))
    monkeypatch.chdir(root)
    yield root
    for name in [m for m in sys.modules if m.startswith("prespkg")]:
        del sys.modules[name]


def _run(*argv):
    return FlexLockRunner().run(list(argv))


# ── addresses ──


def test_canonical_defaults_forms(project):
    assert canonical_defaults("pkg.mod.attr") == "pkg.mod:attr"
    assert canonical_defaults("pkg.mod:attr") == "pkg.mod:attr"
    assert canonical_defaults("prespkg/xps.py:pipe") == "prespkg/xps.py:pipe"
    assert canonical_defaults(str(project / "prespkg/xps.py")) == "prespkg/xps.py:defaults"
    (project / "c.yaml").write_text("a: 1\n")
    assert canonical_defaults("c.yaml") == "c.yaml"


@pytest.mark.parametrize("address", [
    "a.b.xps:train_a", "xps:train_a", "xps.train_a", "train_a", "a.b.xps.train_a",
])
def test_address_suffix_matching(address):
    assert address_matches("a.b.xps:train_a", address)


def test_address_mismatch():
    assert not address_matches("a.b.xps:train_a", "train")
    assert not address_matches("a.b.xps:train_a", "bxps:train_a")


# ── recording ──


def test_preset_never_changes_fingerprint():
    base = {"_target_": "m.f", "save_dir": "out", "x": 1}
    fp = fingerprint(base)
    preset = make_preset("m.cfg", "main", ["x=1"])
    assert fingerprint(dict(base, _preset_=preset)) == fp
    nested = {"_target_": "m.g", "save_dir": "o", "inner": dict(base, _preset_=preset)}
    assert fingerprint(nested) == fingerprint(
        {"_target_": "m.g", "save_dir": "o", "inner": base}
    )


def test_instantiate_strips_preset():
    cfg = {"_target_": "builtins.dict", "a": 1, PRESET_KEY: make_preset("m.c")}
    assert instantiate(cfg) == {"a": 1}


def test_cli_run_records_preset_and_links(project):
    _run("-d", "prespkg.xps.train_a", "-s", "main", "-o", "main.x=5")
    save_dir = project / "results" / "train_a"
    preset = load_record(save_dir)["config"][PRESET_KEY]
    assert preset["defaults"] == "prespkg.xps:train_a"
    assert preset["select"] == "main"
    assert preset["overrides"] == ["main.x=5"]
    link = project / ".flexlock/presets/prespkg.xps:train_a/main/results__train_a"
    assert link.is_symlink() and link.resolve() == save_dir.resolve()


def test_overrides_with_interpolations_stay_literal(project):
    _run("-d", "prespkg.xps.train_a", "-s", "main",
         "-o", "main.x=5", "extra=${results}")
    preset = load_record(project / "results/train_a")["config"][PRESET_KEY]
    assert preset["overrides"][-1] == "extra=${results}"


def test_find_runs_newest_first_and_strict(project):
    _run("-d", "prespkg.xps.train_a", "-s", "main", "-o", "main.x=5",
         "--save-dir-policy", "increment")
    _run("-d", "prespkg.xps.train_a", "-s", "main",
         "--save-dir-policy", "increment")
    runs = find_runs("xps.train_a", select="main")
    assert [r.path.name for r in runs] == ["train_a_0001", "train_a_0000"]
    assert [r.path.name for r in find_runs("train_a", strict=True)] == ["train_a_0001"]
    assert find_runs("train_a", select="other") == []


def test_project_get_records_preset(project):
    proj = Project("prespkg.xps.pipe")
    cfg = proj.get("prep")
    assert cfg[PRESET_KEY]["defaults"] == "prespkg.xps:pipe"
    assert cfg[PRESET_KEY]["select"] == "prep"
    proj.submit(cfg)
    assert [r.select for r in find_runs("xps.pipe")] == ["prep"]


def test_project_get_skips_non_stage_nodes(project):
    proj = Project(OmegaConf.create({"params": {"lr": 1}}))
    assert PRESET_KEY not in proj.get("params")
    proj = Project("prespkg.xps.train_a")
    assert PRESET_KEY not in proj.get("main.model")  # _target_ but no save_dir


def test_multistage_links_each_stage(project):
    _run("-d", "prespkg.xps.pipe", "-s", "prep", "train")
    assert sorted(r.select for r in find_runs("xps.pipe")) == ["prep", "train"]


def test_sweep_tasks_are_linked(project):
    results = project / "results"
    sweep = results / "sweep.yaml"
    sweep.parent.mkdir(parents=True, exist_ok=True)
    sweep.write_text(
        "\n".join(f"- {{x: {i}, save_dir: {results}/sw/item_{i}}}" for i in range(2))
    )
    _run("-d", "prespkg.xps.train_a", "-s", "main", "--sweep-file", str(sweep),
         "--sweep-target", ".", "--n_jobs", "2")
    names = sorted(r.path.name for r in find_runs("train_a"))
    assert names == ["item_0", "item_1"]


def test_reindex_rebuilds_links(project):
    from flexlock.index import reindex

    _run("-d", "prespkg.xps.train_a", "-s", "main")
    shutil.rmtree(project / ".flexlock/presets")
    assert find_runs("train_a") == []
    reindex(project / "results")
    assert len(find_runs("train_a")) == 1


def test_dangling_link_pruned(project):
    _run("-d", "prespkg.xps.train_a", "-s", "main")
    shutil.rmtree(project / "results/train_a")
    assert find_runs("train_a") == []
    assert not any((project / ".flexlock/presets").rglob("results__train_a"))


def test_results_level_flexlock_found_from_project_root(project, tmp_path):
    """Layouts without a project .flexlock/: links live in results/.flexlock."""
    shutil.rmtree(project / ".flexlock")
    _run("-d", "prespkg.xps.train_a", "-s", "main")
    assert (project / "results/.flexlock/presets").is_dir()
    assert project / "results/.flexlock/presets" in presets_roots(project)
    assert len(find_runs("train_a")) == 1


# ── catalogue ──


def test_list_presets(project):
    _run("-d", "prespkg.xps.pipe", "-s", "prep")
    presets = {p["name"]: p for p in list_presets("prespkg.xps")}
    assert set(presets) == {"train_a", "pipe"}
    assert presets["train_a"]["comment"] == (
        "Baseline training run. Second line of the comment."
    )
    assert presets["pipe"]["comment"] == "Pipeline with two stages."
    assert presets["pipe"]["selects"] == ["prep", "train"]
    assert presets["pipe"]["runs"] == {"prep": 1}


def test_cli_runs_and_presets_output(project, capsys):
    from flexlock.cli import main as cli_main

    _run("-d", "prespkg.xps.train_a", "-s", "main", "--note", "baseline")
    sys.argv = ["flexlock", "runs", "xps.train_a", "--format", "json"]
    cli_main()
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["note"] == "baseline" and rows[0]["select"] == "main"

    sys.argv = ["flexlock", "presets", "prespkg.xps", "--format", "md"]
    cli_main()
    out = capsys.readouterr().out
    assert "`flexlock-run -d prespkg.xps.train_a -s main` (1 run)" in out


# ── ${run:...} references (phase 3) ──

DOWN_SRC = '''\
from flexlock import py2cfg
from prespkg.stage import run

infer_a = dict(
    train_dir="${run:xps.train_a,main}",
    main=py2cfg(run, x=9, model="${train_dir}/results.json",
                save_dir="RESULTS/infer_a", log="${.save_dir}/logs"),
)
'''


@pytest.fixture
def down(project):
    (project / "prespkg" / "down.py").write_text(
        DOWN_SRC.replace("RESULTS", str(project / "results"))
    )
    return project


def _train(*extra):
    _run("-d", "prespkg.xps.train_a", "-s", "main",
         "--save-dir-policy", "increment", *extra)


def _model_of(save_dir):
    return load_record(save_dir)["config"]["model"]


def test_run_ref_picks_newest_and_records_lineage(down):
    _train()
    _train()
    _run("-d", "prespkg.down.infer_a", "-s", "main")
    newest = str((down / "results/train_a_0001").resolve())
    record = load_record(down / "results/infer_a")
    assert record["config"]["model"] == f"{newest}/results.json"
    assert newest in record["config"]["_snapshot_"]["prevs"]
    assert any(v.get("path") == newest for v in record["lineage"].values())


def test_run_ref_pin_and_strict(down):
    _train()
    _train("-o", "main.x=7")
    _run("-d", "prespkg.down.infer_a", "-s", "main",
         "-o", "train_dir=${run:xps.train_a,main,0000}")
    assert "train_a_0000/" in _model_of(down / "results/infer_a")
    _run("-d", "prespkg.down.infer_a", "-s", "main", "--force",
         "-o", "train_dir=${run:xps.train_a,main,strict}")
    assert "train_a_0000/" in _model_of(down / "results/infer_a")


def test_run_ref_resolved_before_save_dir_policy(down):
    """Relative refs stay live: log follows the incremented save_dir."""
    _train()
    _run("-d", "prespkg.down.infer_a", "-s", "main",
         "--save-dir-policy", "increment")
    config = load_record(down / "results/infer_a_0000")["config"]
    assert config["log"].endswith("infer_a_0000/logs")


def test_run_ref_skips_incomplete_runs(down):
    _train()
    _train()
    (down / "results/train_a_0001/run.complete").unlink()
    _run("-d", "prespkg.down.infer_a", "-s", "main")
    assert "train_a_0000/" in _model_of(down / "results/infer_a")


def test_run_ref_errors(down):
    from flexlock.exceptions import FlexLockConfigError

    with pytest.raises(Exception, match="no complete run of preset xps.train_a"):
        _run("-d", "prespkg.down.infer_a", "-s", "main")
    _run("-d", "prespkg.xps.pipe", "-s", "prep", "train")
    from flexlock.presets import resolve_run

    with pytest.raises(FlexLockConfigError, match="several -s keys"):
        resolve_run("xps.pipe")
    _train()
    with pytest.raises(FlexLockConfigError, match=r"Complete runs of this preset: train_a_0000"):
        resolve_run("xps.train_a", "main", "0009")


def test_dump_and_enqueue_show_concrete_run(down, capsys):
    _train()
    _run("-d", "prespkg.down.infer_a", "-s", "main", "--dump")
    out = capsys.readouterr().out
    assert "${run:" not in out and "train_a_0000/results.json" in out
    queue = down / "queue.yaml"
    _run("-d", "prespkg.down.infer_a", "-s", "main", "--enqueue", str(queue))
    assert "train_a_0000/results.json" in queue.read_text()


def test_project_get_keeps_ref_until_submit(down):
    _train()
    proj = Project("prespkg.down.infer_a")
    cfg = proj.get("main")
    raw = OmegaConf.to_container(cfg, resolve=False)["model"]
    assert raw.startswith("${run:xps.train_a,main}")
    result = proj.submit(cfg)
    assert "train_a_0000" in _model_of(result.save_dir)


def test_run_ref_in_sweep_items(down):
    _train()
    _train()
    results = down / "results"
    sweep = results / "sweep.yaml"
    sweep.write_text(
        f"- {{train_dir: '${{run:xps.train_a,main,0000}}', "
        f"save_dir: {results}/sw/i0}}\n"
        f"- {{train_dir: '${{run:xps.train_a,main}}', save_dir: {results}/sw/i1}}\n"
    )
    _run("-d", "prespkg.down.infer_a", "-s", "main", "--sweep-file", str(sweep),
         "--sweep-target", ".", "--n_jobs", "2")
    assert "train_a_0000/" in load_record(results / "sw/i0")["config"]["train_dir"] + "/"
    assert load_record(results / "sw/i1")["config"]["train_dir"].endswith("train_a_0001")
