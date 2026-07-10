"""Tests for RunRecord — the single on-disk contract owner (Phase 3.1)."""

import json
from pathlib import Path

from flexlock.run_record import (
    RunRecord,
    STATUS_DONE,
    STATUS_INCOMPLETE,
    STATUS_MISSING,
)


def test_status_lifecycle(tmp_path):
    rec = RunRecord(tmp_path / "run")
    assert rec.status == STATUS_MISSING
    assert not rec.is_complete

    rec.write_lock({"config": {"lr": 0.1}})
    assert rec.status == STATUS_INCOMPLETE
    assert not rec.is_complete

    rec.mark_complete(result={"acc": 0.9})
    assert rec.status == STATUS_DONE
    assert rec.is_complete


def test_write_lock_roundtrip(tmp_path):
    rec = RunRecord(tmp_path / "run")
    snap = {"config": {"lr": 0.1, "save_dir": "run"}, "timestamp": "t"}
    rec.write_lock(snap)
    loaded = rec.load()
    assert loaded["config"]["lr"] == 0.1


def test_write_results_dict_and_scalar(tmp_path):
    rec = RunRecord(tmp_path / "run")
    rec.write_results({"acc": 0.9})
    assert rec.load_results() == {"acc": 0.9}

    rec2 = RunRecord(tmp_path / "run2")
    rec2.write_results(42)
    assert rec2.load_results() == {"result": 42}


def test_mark_complete_payload(tmp_path):
    rec = RunRecord(tmp_path / "run")
    marker = rec.mark_complete(result={"x": 1})
    payload = json.loads(Path(marker).read_text())
    assert payload["has_result"] is True
    assert "ts" in payload and "version" in payload


def test_load_missing_returns_none(tmp_path):
    rec = RunRecord(tmp_path / "nope")
    assert rec.load() is None
    assert rec.load_results() is None


def test_writes_are_atomic_no_tmp_left(tmp_path):
    rec = RunRecord(tmp_path / "run")
    rec.write_lock({"config": {}})
    rec.write_results({"a": 1})
    rec.mark_complete()
    leftovers = [p.name for p in (tmp_path / "run").iterdir()]
    assert sorted(leftovers) == ["results.json", "run.complete", "run.lock"]


# ── run.error (Phase A1) ──


def test_write_error_payload_shape(tmp_path):
    rec = RunRecord(tmp_path / "run")
    try:
        raise ValueError("boom")
    except ValueError as exc:
        rec.write_error(exc, task_id="abc", node="node1")

    payload = rec.load_error()
    assert payload["version"] == 1
    assert payload["exc_type"] == "ValueError"
    assert payload["exc_message"] == "boom"
    assert "ValueError: boom" in payload["traceback"]
    assert payload["task_id"] == "abc"
    assert payload["node"] == "node1"
    assert "timestamp" in payload


def test_load_error_missing_returns_none(tmp_path):
    assert RunRecord(tmp_path / "run").load_error() is None


def test_mark_complete_clears_error(tmp_path):
    rec = RunRecord(tmp_path / "run")
    try:
        raise RuntimeError("fail")
    except RuntimeError as exc:
        rec.write_error(exc)
    assert rec.error_path.exists()

    rec.mark_complete(result={"acc": 1.0})
    assert not rec.error_path.exists()
    assert rec.load_error() is None


def test_write_error_never_raises(tmp_path, monkeypatch):
    rec = RunRecord(tmp_path / "run")

    # Force the atomic write to blow up; write_error must swallow it.
    import flexlock.run_record as rr

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(rr, "_atomic_write", _boom)
    try:
        raise ValueError("original")
    except ValueError as exc:
        # Must not raise despite the write failure.
        assert rec.write_error(exc) is None
