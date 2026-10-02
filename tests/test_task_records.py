"""Phase 1: task records in the task dir (task_record="dir") and one reader."""

import sys
from pathlib import Path

import pytest
import yaml
from git import Repo
from omegaconf import OmegaConf

from flexlock.api import Project
from flexlock.parallel import ParallelExecutor
from flexlock.record import (
    MARKER_NAME,
    find_run_dir,
    iter_run_dirs,
    load_record,
    read_lock,
)
from flexlock.utils import instantiate

MOD_SRC = "def run(save_dir, x=1):\n    return {'x': x}\n"


@pytest.fixture
def recpkg(tmp_path, monkeypatch):
    """A git repo holding an importable package ``recpkg`` (spawn-safe)."""
    repo_dir = tmp_path / "repo"
    pkg = repo_dir / "recpkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "stage.py").write_text(MOD_SRC)
    repo = Repo.init(repo_dir)
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["recpkg/__init__.py", "recpkg/stage.py"])
    repo.index.commit("init")
    monkeypatch.syspath_prepend(str(repo_dir))
    monkeypatch.setenv("PYTHONPATH", str(repo_dir))
    yield repo_dir
    for name in [m for m in sys.modules if m.startswith("recpkg")]:
        del sys.modules[name]


def _task(save_dir, x):
    return {"_target_": "recpkg.stage.run", "save_dir": str(save_dir), "x": x}


def _drain(root, tasks, task_record, task_target=None, base=None):
    base = base or OmegaConf.create({"save_dir": str(root)})
    ParallelExecutor(
        func=instantiate, tasks=tasks, task_target=task_target, cfg=base,
        n_jobs=1, task_record=task_record,
    ).run()


def _assert_full(record, x):
    assert record is not None
    assert record["config"]["x"] == x
    assert "tree" in record["repos"]["recpkg"]
    assert record["fingerprint"]


# ── where the record lives ──


def test_dir_mode_writes_full_record_per_task(recpkg, tmp_path):
    root = tmp_path / "sweep"
    _drain(root, [_task(root / f"t{i}", i) for i in range(3)], "dir")
    for i in range(3):
        lock = read_lock(root / f"t{i}")
        _assert_full(lock, i)
        assert lock["task_id"]
        assert lock["parent"].endswith("run.lock")
        assert (root / f"t{i}" / MARKER_NAME).exists()
    assert read_lock(root)["task_record"] == "dir"


def test_db_mode_keeps_task_dirs_lock_free(recpkg, tmp_path):
    root = tmp_path / "sweep"
    _drain(root, [_task(root / f"t{i}", i) for i in range(2)], "db")
    for i in range(2):
        assert read_lock(root / f"t{i}") is None
        _assert_full(load_record(root / f"t{i}"), i)


def test_env_var_selects_default(recpkg, tmp_path, monkeypatch):
    monkeypatch.setenv("FLEXLOCK_TASK_RECORD", "db")
    root = tmp_path / "sweep"
    _drain(root, [_task(root / "t0", 0)], None)
    assert read_lock(root)["task_record"] == "db"
    assert read_lock(root / "t0") is None


def test_invalid_task_record_rejected(tmp_path):
    with pytest.raises(ValueError, match="task_record"):
        ParallelExecutor(
            func=instantiate, tasks=[{}], task_target=None,
            cfg=OmegaConf.create({"save_dir": str(tmp_path)}), task_record="file",
        )


@pytest.mark.parametrize("mode", ["dir", "db"])
def test_single_task_in_master_dir(recpkg, tmp_path, mode):
    """HPC single run: the task's save_dir is the master dir."""
    root = tmp_path / "single"
    _drain(root, [_task(root, 7)], mode)
    record = load_record(root)
    _assert_full(record, 7)
    lock = read_lock(root)
    if mode == "dir":
        assert lock["task_id"] and "parent" not in lock
    else:
        assert "task_id" not in lock  # master stub stays; record is in the DB


def test_shared_save_dir_keeps_first_record_only(recpkg, tmp_path):
    root = tmp_path / "sweep"
    shared = root / "shared"
    _drain(root, [_task(shared, 1), _task(shared, 2)], "dir")
    lock = read_lock(shared)
    assert lock["config"]["x"] in (1, 2)  # one task owns the file, not clobbered


# ── the reader ──


def test_serial_run_record(recpkg, tmp_path):
    save_dir = tmp_path / "serial"
    Project().submit(OmegaConf.create(_task(save_dir, 3)))
    _assert_full(load_record(save_dir), 3)


def test_iter_run_dirs_and_find_run_dir(recpkg, tmp_path):
    root = tmp_path / "sweep"
    _drain(root, [_task(root / f"t{i}", i) for i in range(2)], "db")
    dirs = list(iter_run_dirs(root))
    assert dirs == sorted([root, root / "t0", root / "t1"])
    (root / "t0" / "out").mkdir()
    assert find_run_dir(root / "t0" / "out") == str(root / "t0")


@pytest.mark.parametrize("mode", ["dir", "db"])
def test_consumers_see_task_records(recpkg, tmp_path, mode):
    from flexlock.diff_cli import load_snapshot_from_dir, run_comparison
    from flexlock.index import reindex, resolve_index_path
    from flexlock.query import load_run_summary
    from flexlock.resolvers import run_lock_resolver

    root = tmp_path / "sweep"
    _drain(root, [_task(root / f"t{i}", i) for i in range(2)], mode)
    t0, t1 = root / "t0", root / "t1"

    is_match, diffs = run_comparison(
        load_snapshot_from_dir(t0), load_snapshot_from_dir(t1)
    )
    assert not is_match and "config" in diffs and "git" not in diffs

    assert run_lock_resolver(str(t1), "config.x") == 1

    summary = load_run_summary(t0)
    assert "recpkg" in summary["repos"] and summary["fingerprint"]

    index_path = resolve_index_path(root)
    index_path.unlink(missing_ok=True)
    assert reindex(root) == 2


def test_sweep_rerun_does_not_trip_collision_guard(recpkg, tmp_path):
    """Task dirs now hold run.lock; re-running the sweep resumes via the DB."""
    root = tmp_path / "sweep"
    base = OmegaConf.create(_task(root / "base", 0))
    sweep = [{"x": i, "save_dir": str(root / f"item_{i}")} for i in (1, 2)]
    proj = Project()
    first = proj.submit(base.copy(), sweep=sweep, n_jobs=2)
    assert all(r.is_success for r in first)
    assert read_lock(root / "item_1")["task_id"]
    again = proj.submit(base.copy(), sweep=sweep, n_jobs=2)
    assert all(r.is_success for r in again)


def test_gc_protects_inside_and_containing_dirs(tmp_path):
    from flexlock.cli import _is_protected

    master = (tmp_path / "sweep").resolve()
    task = master / "t0"
    other = (tmp_path / "other").resolve()
    assert _is_protected(task, [master])      # task inside tagged master
    assert _is_protected(master, [task])      # master contains tagged task
    assert not _is_protected(other, [master])


def test_export_materializes_master_fields(recpkg, tmp_path):
    from flexlock.export import export_all_tasks

    root = tmp_path / "sweep"
    _drain(root, [_task(root / "t0", 0)], "db")
    out = tmp_path / "export"
    export_all_tasks(root / "run.lock.tasks.db", out)
    (exported,) = list(out.glob("task_*/run.lock"))
    assert "recpkg" in yaml.safe_load(exported.read_text())["repos"]


@pytest.mark.parametrize("mode", ["dir", "db"])
def test_pipeline_stages_keep_distinct_records_and_upstream_refs(recpkg, tmp_path, mode, monkeypatch):
    """A downstream stage must read the upstream record before the row finishes."""
    from flexlock.freeze import freeze_deferred
    from flexlock.index import reindex, resolve_index_path
    from flexlock.presets import attach, make_preset, presets_dir
    from flexlock.taskdb import get_all_tasks, get_task_snapshot

    monkeypatch.setattr("flexlock.worker.random.uniform", lambda a, b: 0)
    monkeypatch.setenv("FLEXLOCK_TASK_RECORD", mode)
    root = tmp_path / "pipeline"
    a, b = root / "a", root / "b"
    first = OmegaConf.create(_task(a, 7))
    second = OmegaConf.create(_task(b, f"${{run_lock:{a},config.x}}"))
    for name, cfg in (("a", first), ("b", second)):
        attach(cfg, make_preset("recpkg.stage", name))
    results = Project().submit_pipeline([[freeze_deferred(first), freeze_deferred(second)]])
    assert all(result.is_success for result in results[0])
    assert [result.result["x"] for result in results[0]] == [7, 7]
    for name, path in (("a", a), ("b", b)):
        record = load_record(path)
        _assert_full(record, 7)
        assert record["config"]["save_dir"] == str(path)
        assert record["config"]["_preset_"]["select"] == name
        assert bool(read_lock(path)) == (mode == "dir")
        defaults = record["config"]["_preset_"]["defaults"]
        links = list((presets_dir(path) / defaults / name).iterdir())
        assert any(link.resolve() == path for link in links)
    row = get_all_tasks(root / "run.lock.tasks.db")[0]
    snapshot = get_task_snapshot(root / "run.lock.tasks.db", row["task_id"])
    assert set(snapshot["stages"]) == {str(a.resolve()), str(b.resolve())}
    resolve_index_path(root).unlink(missing_ok=True)
    assert reindex(root) == 2


def test_composite_export_materializes_each_stage(recpkg, tmp_path, monkeypatch):
    from flexlock.export import export_task
    from flexlock.diff_cli import load_snapshot_from_db
    from flexlock.taskdb import get_all_tasks

    monkeypatch.setattr("flexlock.worker.random.uniform", lambda a, b: 0)
    root = tmp_path / "pipeline"
    _drain(root, [{"_stages_": [_task(root / "a", 1), _task(root / "b", 2)]}], "db")
    db = root / "run.lock.tasks.db"
    row = get_all_tasks(db)[0]
    exported = tmp_path / "exported"
    export_task(db, row["task_id"], exported)
    record = read_lock(exported)
    for i, name in enumerate(("a", "b"), 1):
        _assert_full(record["stages"][str((root / name).resolve())], i)
    with pytest.raises(ValueError, match="stage directories"):
        load_snapshot_from_db(db, row["task_id"])
