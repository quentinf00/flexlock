"""Phase 0: sweep/HPC tasks record their code, and drift after the snapshot is flagged."""

import importlib
import json
import os
import sqlite3
import sys
import time

import pytest
import yaml
from git import Repo
from omegaconf import OmegaConf

from flexlock.git_utils import code_drift, create_shadow_snapshot
from flexlock.parallel import ParallelExecutor
from flexlock.utils import collect_task_repos

MOD_SRC = "def run(save_dir, x=1):\n    return {'x': x}\n"


@pytest.fixture
def drift_pkg(tmp_path, monkeypatch):
    """A git repo holding an importable package ``driftpkg``."""
    repo_dir = tmp_path / "repo"
    pkg = repo_dir / "driftpkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "stage.py").write_text(MOD_SRC)
    (repo_dir / ".gitignore").write_text("ignored/\n")
    repo = Repo.init(repo_dir)
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["driftpkg/__init__.py", "driftpkg/stage.py", ".gitignore"])
    repo.index.commit("init")

    monkeypatch.syspath_prepend(str(repo_dir))
    for name in [m for m in sys.modules if m.startswith("driftpkg")]:
        del sys.modules[name]
    yield repo_dir
    for name in [m for m in sys.modules if m.startswith("driftpkg")]:
        del sys.modules[name]


def _snapshot_repos(repo_dir):
    snap = create_shadow_snapshot(str(repo_dir))
    return {"driftpkg": {"path": str(repo_dir), "tree": snap["tree"]}}


def _touch_later(path, content):
    path.write_text(content)
    future = time.time() + 5
    os.utime(path, (future, future))


def test_no_drift_when_loaded_code_matches_tree(drift_pkg):
    repos = _snapshot_repos(drift_pkg)
    since = time.time()
    importlib.import_module("driftpkg.stage")
    # Touched but unchanged: mtime passes the pre-filter, blob hash matches.
    _touch_later(drift_pkg / "driftpkg" / "stage.py", MOD_SRC)
    assert code_drift(repos, since) == {}


def test_edited_loaded_module_is_drift(drift_pkg):
    repos = _snapshot_repos(drift_pkg)
    since = time.time()
    importlib.import_module("driftpkg.stage")
    _touch_later(drift_pkg / "driftpkg" / "stage.py", MOD_SRC + "# edited\n")
    assert code_drift(repos, since) == {"driftpkg": ["driftpkg/stage.py"]}


def test_edit_to_unloaded_module_is_not_drift(drift_pkg):
    repos = _snapshot_repos(drift_pkg)
    since = time.time()
    importlib.import_module("driftpkg")  # stage.py never imported
    _touch_later(drift_pkg / "driftpkg" / "stage.py", MOD_SRC + "# edited\n")
    assert code_drift(repos, since) == {}


def test_new_module_after_snapshot_is_drift_unless_ignored(drift_pkg):
    repos = _snapshot_repos(drift_pkg)
    since = time.time()
    _touch_later(drift_pkg / "driftpkg" / "late.py", "Y = 1\n")
    ignored = drift_pkg / "ignored"
    ignored.mkdir()
    _touch_later(ignored / "vendored.py", "Z = 1\n")
    importlib.import_module("driftpkg.late")
    sys.path.insert(0, str(ignored))
    try:
        importlib.import_module("vendored")
        assert code_drift(repos, since) == {"driftpkg": ["driftpkg/late.py"]}
    finally:
        sys.path.remove(str(ignored))
        sys.modules.pop("vendored", None)


def test_collect_task_repos_from_task_targets(drift_pkg, tmp_path):
    base = OmegaConf.create({"save_dir": str(tmp_path / "out")})
    tasks = [
        {"_target_": "driftpkg.stage.run", "save_dir": str(tmp_path / f"t{i}")}
        for i in range(3)
    ]
    assert collect_task_repos(base, [], None) == {}
    repos = collect_task_repos(base, tasks, None)
    assert list(repos) == ["driftpkg"]
    assert os.path.realpath(repos["driftpkg"]["path"]) == os.path.realpath(drift_pkg)


def _run_single_task_sweep(tmp_path, func):
    """A sweep whose only task carries the full config (single HPC run shape)."""
    save_dir = tmp_path / "run"
    base = OmegaConf.create({"save_dir": str(save_dir)})
    task = {"_target_": "driftpkg.stage.run", "save_dir": str(save_dir), "x": 2}
    ParallelExecutor(
        func=func, tasks=[task], task_target=None, cfg=base, n_jobs=1
    ).run()
    master = yaml.safe_load((save_dir / "run.lock").read_text())
    conn = sqlite3.connect(save_dir / "run.lock.tasks.db")
    (snap,) = conn.execute("SELECT snapshot FROM tasks").fetchone()
    conn.close()
    return master, json.loads(snap)


def test_single_task_sweep_records_repos_in_master(drift_pkg, tmp_path):
    from flexlock.utils import instantiate

    master, task_snap = _run_single_task_sweep(tmp_path, instantiate)
    assert "tree" in master["repos"]["driftpkg"]
    assert "code_drift" not in task_snap


def test_task_edited_during_run_records_drift(drift_pkg, tmp_path):
    from flexlock.utils import instantiate

    def edit_then_run(cfg):
        out = instantiate(cfg)  # imports driftpkg.stage
        _touch_later(drift_pkg / "driftpkg" / "stage.py", MOD_SRC + "# edited\n")
        return out

    _, task_snap = _run_single_task_sweep(tmp_path, edit_then_run)
    assert task_snap["code_drift"] == {"driftpkg": ["driftpkg/stage.py"]}


def test_serial_run_lock_gets_drift(drift_pkg, tmp_path):
    from flexlock.snapshot import record_code_drift, snapshot

    save_dir = tmp_path / "serial"
    cfg = OmegaConf.create({"_target_": "driftpkg.stage.run", "save_dir": str(save_dir)})
    snapshot(cfg, repos={"driftpkg": {"path": str(drift_pkg)}})
    assert record_code_drift(save_dir) == {}

    importlib.import_module("driftpkg.stage")
    _touch_later(drift_pkg / "driftpkg" / "stage.py", MOD_SRC + "# edited\n")
    assert record_code_drift(save_dir) == {"driftpkg": ["driftpkg/stage.py"]}
    lock = yaml.safe_load((save_dir / "run.lock").read_text())
    assert lock["code_drift"] == {"driftpkg": ["driftpkg/stage.py"]}
