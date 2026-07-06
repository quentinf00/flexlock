"""Tests for the project-wide fingerprint index (Phase 2.2)."""

import pytest
from pathlib import Path

from flexlock import index
from flexlock.index import (
    IndexRow,
    LOCATION_RUN_LOCK,
    LOCATION_TASK,
    resolve_index_path,
)
from flexlock.run_record import RunRecord


# ── location resolution ──


def test_resolve_prefers_env(tmp_path, monkeypatch):
    forced = tmp_path / "custom" / "idx.db"
    monkeypatch.setenv("FLEXLOCK_INDEX", str(forced))
    assert resolve_index_path(tmp_path / "a" / "b") == forced


def test_resolve_walks_up_to_existing(tmp_path, monkeypatch):
    monkeypatch.delenv("FLEXLOCK_INDEX", raising=False)
    root = tmp_path / "proj"
    (root / ".flexlock").mkdir(parents=True)
    existing = root / ".flexlock" / "index.db"
    existing.write_text("")  # exists
    deep = root / "outputs" / "exp" / "run_0000"
    deep.mkdir(parents=True)
    assert resolve_index_path(deep) == existing


def test_resolve_defaults_to_base(tmp_path, monkeypatch):
    monkeypatch.delenv("FLEXLOCK_INDEX", raising=False)
    base = tmp_path / "results"
    base.mkdir()
    assert resolve_index_path(base) == base / ".flexlock" / "index.db"


# ── round-trip: serial run ──


def _complete_run_dir(path: Path):
    rec = RunRecord(path)
    rec.write_lock({"config": {"lr": 0.1}})
    rec.write_results({"acc": 0.9})
    rec.mark_complete(result={"acc": 0.9})


def test_record_and_lookup_run_lock(tmp_path, monkeypatch):
    monkeypatch.delenv("FLEXLOCK_INDEX", raising=False)
    search_root = tmp_path / "outputs"
    run_dir = search_root / "run_0000"
    _complete_run_dir(run_dir)

    index.record_run_lock(run_dir, "fp-abc")
    row = index.lookup(search_root, "fp-abc")
    assert row is not None
    assert row.location_kind == LOCATION_RUN_LOCK
    resolved = index.verify_and_resolve(search_root, row)
    assert resolved == run_dir


def test_only_done_rows_served(tmp_path, monkeypatch):
    monkeypatch.delenv("FLEXLOCK_INDEX", raising=False)
    search_root = tmp_path / "outputs"
    idx = resolve_index_path(search_root, create_parent=True)
    # A failed run recorded with status != done must never be looked up.
    index.upsert(
        idx,
        fingerprint="fp-fail",
        location_kind=LOCATION_RUN_LOCK,
        save_dir=str(search_root / "run_x"),
        status="failed",
    )
    assert index.lookup(search_root, "fp-fail") is None


def test_stale_pointer_self_prunes(tmp_path, monkeypatch):
    monkeypatch.delenv("FLEXLOCK_INDEX", raising=False)
    search_root = tmp_path / "outputs"
    run_dir = search_root / "run_0000"
    _complete_run_dir(run_dir)
    index.record_run_lock(run_dir, "fp-stale")

    # Delete the run's completion marker -> pointer is now stale.
    (run_dir / "run.complete").unlink()

    row = index.lookup(search_root, "fp-stale")
    assert row is not None  # row still present
    assert index.verify_and_resolve(search_root, row) is None  # verifies + prunes
    assert index.lookup(search_root, "fp-stale") is None  # pruned


# ── round-trip: sweep task (first-class) ──


def test_task_location_first_class(tmp_path, monkeypatch):
    monkeypatch.delenv("FLEXLOCK_INDEX", raising=False)
    sweep_root = tmp_path / "sweep"
    task_dir = sweep_root / "sweep_0001"
    # A task dir carries run.complete + results.json but no run.lock.
    rec = RunRecord(task_dir)
    rec.write_results({"acc": 0.5})
    rec.mark_complete(result={"acc": 0.5})
    db_path = sweep_root / "run.lock.tasks.db"
    db_path.write_text("")  # placeholder

    index.record_task(task_dir, db_path, "task123", "fp-task")
    row = index.lookup(sweep_root, "fp-task")
    assert row is not None
    assert row.location_kind == LOCATION_TASK
    assert index.verify_and_resolve(sweep_root, row) == task_dir


# ── reindex ──


def test_reindex_backfills_run_lock(tmp_path, monkeypatch):
    monkeypatch.delenv("FLEXLOCK_INDEX", raising=False)
    root = tmp_path / "results"
    run_dir = root / "exp" / "run_0000"
    rec = RunRecord(run_dir)
    rec.write_lock({"config": {"lr": 0.1}, "fingerprint": "fp-reidx"})
    rec.mark_complete(result={"x": 1})

    n = index.reindex(root)
    assert n == 1
    row = index.lookup(root / "exp", "fp-reidx")
    assert row is not None and row.location_kind == LOCATION_RUN_LOCK


# ── end-to-end via the public API ──


def _payload(lr=0.01, save_dir=None):
    return {"lr": lr, "doubled": lr * 2}


def test_end_to_end_index_cache_hit(tmp_path, monkeypatch):
    """A completed serial submit is found via the index on re-lookup."""
    monkeypatch.setenv("FLEXLOCK_INDEX", str(tmp_path / "idx.db"))
    from flexlock.api import Project
    from omegaconf import OmegaConf

    out = tmp_path / "outputs"
    cfg = OmegaConf.create(
        {
            "_target_": "tests.test_index._payload",
            "lr": 0.01,
            "save_dir": str(out / "run_0000"),
        }
    )
    proj = Project()
    proj.submit(cfg, smart_run=True, search_dirs=[str(out)])

    assert (tmp_path / "idx.db").exists()
    match = proj._find_matching_run(cfg, search_dirs=[str(out)])
    assert match == out / "run_0000"


def test_index_serves_hit_without_glob_fallback(tmp_path, monkeypatch):
    """With the glob fallback disabled, the hit must come from the index."""
    monkeypatch.setenv("FLEXLOCK_INDEX", str(tmp_path / "idx.db"))
    monkeypatch.setenv("FLEXLOCK_INDEX_FALLBACK", "0")
    from flexlock.api import Project
    from omegaconf import OmegaConf

    out = tmp_path / "outputs"
    cfg = OmegaConf.create(
        {
            "_target_": "tests.test_index._payload",
            "lr": 0.02,
            "save_dir": str(out / "run_0000"),
        }
    )
    proj = Project()
    proj.submit(cfg, smart_run=True, search_dirs=[str(out)])

    # get_result resolves the cached run through the index only.
    res = proj.get_result(cfg, search_dirs=[str(out)])
    assert res.status == "CACHED"
    assert res.get("doubled") == 0.04


def test_reindex_skips_incomplete_and_unfingerprinted(tmp_path, monkeypatch):
    monkeypatch.delenv("FLEXLOCK_INDEX", raising=False)
    root = tmp_path / "results"

    # incomplete (no run.complete)
    inc = RunRecord(root / "a")
    inc.write_lock({"config": {}, "fingerprint": "fp-a"})

    # complete but no fingerprint stored (legacy)
    legacy = RunRecord(root / "b")
    legacy.write_lock({"config": {}})
    legacy.mark_complete()

    assert index.reindex(root) == 0
