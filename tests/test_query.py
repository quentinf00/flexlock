"""Tests for the read-only query layer (Phase B) and `flexlock show`."""

import json
from pathlib import Path

import pytest
import yaml

from flexlock import query
from flexlock.run_record import RunRecord


def _make_run(base, name, *, config=None, note=None, timestamp="2026-03-15T10:00:00",
              lineage=None, complete=False, error=None, results=None):
    run_dir = Path(base) / name
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = config or {"_target_": "mod.func", "save_dir": str(run_dir)}
    data = {"timestamp": timestamp, "config": cfg}
    if note is not None:
        data["note"] = note
    if lineage:
        data["lineage"] = lineage
    (run_dir / "run.lock").write_text(yaml.dump(data))
    rec = RunRecord(run_dir)
    if results is not None:
        rec.write_results(results)
    if complete:
        rec.mark_complete(result=results)
    if error is not None:
        try:
            raise ValueError(error)
        except ValueError as exc:
            rec.write_error(exc)
    return run_dir


# ── run_status ──


def test_status_complete(tmp_path):
    d = _make_run(tmp_path, "run_ok", complete=True, results={"acc": 0.9})
    st = query.run_status(d)
    assert st["status"] == "complete"
    assert st["kind"] == "run"


def test_status_failed(tmp_path):
    d = _make_run(tmp_path, "run_bad", error="kaboom")
    st = query.run_status(d)
    assert st["status"] == "failed"
    assert st["error"]["exc_type"] == "ValueError"


def test_status_bare_lock_interrupted(tmp_path):
    d = _make_run(tmp_path, "run_bare")
    st = query.run_status(d)
    assert st["status"] == "interrupted"
    assert "running in-process" in st["detail"]


def test_status_unknown(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert query.run_status(empty)["status"] == "unknown"


# ── sweep task + master via a real task DB ──


def _seed_task_db(sweep_root, task, status):
    from flexlock import taskdb

    db_path = Path(sweep_root) / query.TASKS_DB_NAME
    taskdb.queue_tasks(db_path, [task], tag="t")
    tid = taskdb._hash_task(task)
    if status == "done":
        taskdb.finish_task(db_path, task, result={"x": 1})
    elif status == "failed":
        taskdb.finish_task(db_path, task, error="boom")
    return db_path, tid


def test_status_sweep_task(tmp_path):
    sweep_root = tmp_path / "sweep"
    sweep_root.mkdir()
    (sweep_root / "run.lock").write_text(yaml.dump(
        {"timestamp": "t", "config": {"save_dir": str(sweep_root)}, "note": "batch"}))
    task = {"task_id": 3, "save_dir": str(sweep_root / "sweep_0000")}
    db_path, tid = _seed_task_db(sweep_root, task, "done")

    task_dir = sweep_root / "sweep_0000"
    task_dir.mkdir()
    (task_dir / query.MARKER_NAME).write_text(json.dumps(
        {"db": query.TASKS_DB_NAME, "task_id": tid}))

    st = query.run_status(task_dir)
    assert st["kind"] == "sweep_task"
    assert st["status"] == "complete"


def test_status_sweep_master_aggregation(tmp_path):
    sweep_root = tmp_path / "sweep2"
    sweep_root.mkdir()
    (sweep_root / "run.lock").write_text(yaml.dump(
        {"timestamp": "t", "config": {"save_dir": str(sweep_root)}}))
    from flexlock import taskdb

    db_path = sweep_root / query.TASKS_DB_NAME
    t_ok = {"task_id": 0}
    t_bad = {"task_id": 1}
    taskdb.queue_tasks(db_path, [t_ok, t_bad], tag="t")
    taskdb.finish_task(db_path, t_ok, result={"x": 1})
    taskdb.finish_task(db_path, t_bad, error="boom")

    st = query.run_status(sweep_root)
    assert st["kind"] == "sweep_master"
    assert st["status"] == "failed"
    assert st["tasks"]["done"] == 1
    assert st["tasks"]["failed"] == 1


# ── load_run_summary ──


def test_summary_json_contract(tmp_path):
    up = _make_run(tmp_path, "extract", complete=True, timestamp="2026-01-01T00:00:00")
    down = _make_run(
        tmp_path, "train", complete=True, note="baseline",
        results={"acc": 0.93},
        config={"_target_": "proj.train", "save_dir": str(tmp_path / "train"), "lr": 0.1},
        lineage={"extract": {"path": str(up)}},
    )
    summary = query.load_run_summary(down, scan_root=tmp_path)
    assert summary["schema_version"] == 1
    assert summary["status"] == "complete"
    assert summary["note"] == "baseline"
    assert summary["target"] == "proj.train"
    assert summary["results"]["acc"] == 0.93
    assert summary["lineage"]["upstream"][0]["name"] == "extract"
    # down is upstream's downstream
    up_summary = query.load_run_summary(up, scan_root=tmp_path)
    assert any(Path(d["path"]).name == "train"
               for d in up_summary["lineage"]["downstream"])
    # round-trips through JSON
    json.loads(json.dumps(summary, default=str))


def test_summary_error_attached(tmp_path):
    d = _make_run(tmp_path, "boom", error="explode")
    summary = query.load_run_summary(d, scan_root=tmp_path, downstream=False)
    assert summary["status"] == "failed"
    assert summary["error"]["exc_message"] == "explode"


# ── cmd_show ──


def test_cmd_show_json(tmp_path, capsys):
    d = _make_run(tmp_path, "showme", complete=True, results={"acc": 0.5})
    from flexlock.cli import main
    from unittest.mock import patch

    with patch("sys.argv", ["flexlock", "show", str(d), "--format", "json"]):
        main()
    data = json.loads(capsys.readouterr().out)
    assert data["path"] == str(d.resolve())
    assert data["status"] == "complete"


def test_cmd_show_md(tmp_path, capsys):
    d = _make_run(tmp_path, "showmd", error="nope", note="trying things")
    from flexlock.cli import main
    from unittest.mock import patch

    with patch("sys.argv", ["flexlock", "show", str(d), "--no-downstream"]):
        main()
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "## Error" in out
    assert "trying things" in out
