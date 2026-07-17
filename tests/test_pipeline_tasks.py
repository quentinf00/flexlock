"""Tests for composite pipeline tasks (multi-stage × sweep × HPC × enqueue).

A composite task is a task-DB entry of the form ``{"_stages_": [cfg, ...]}``:
the worker runs its stages sequentially (intra-item ordering by construction),
while parallelism fans out across items. See docs/dev_plan_pipeline_tasks.md.
"""

import json
from pathlib import Path

import pytest
import yaml
from omegaconf import OmegaConf

from flexlock.taskdb import queue_tasks, get_all_tasks
from flexlock.worker import worker_loop


# ---------------------------------------------------------------------------
# Targets (imported by the worker via _target_, so they must be module-level)
# ---------------------------------------------------------------------------

def record_stage(name, save_dir, log, upstream=None, fail=False):
    """Append this stage's name to a shared log file; optionally assert the
    upstream stage dir exists (ordering guarantee) or fail on purpose."""
    if upstream is not None:
        assert Path(upstream).exists(), f"upstream {upstream} not on disk yet"
    with open(log, "a") as fh:
        fh.write(name + "\n")
    if fail:
        raise RuntimeError(f"stage {name} failed on purpose")
    return {"name": name}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TARGET = "tests.test_pipeline_tasks.record_stage"


def _stage(name, root, **extra):
    return {
        "_target_": TARGET,
        "name": name,
        "save_dir": str(Path(root) / name),
        "log": str(Path(root) / "order.log"),
        **extra,
    }


def _read_order(root):
    log = Path(root) / "order.log"
    return log.read_text().split() if log.exists() else []


@pytest.fixture(autouse=True)
def _fast_worker(monkeypatch):
    """Skip the worker's stagger sleep so tests stay fast."""
    monkeypatch.setattr("flexlock.worker.random.uniform", lambda a, b: 0)


def _run_worker(db_path):
    worker_loop(None, OmegaConf.create({}), None, db_path)


def _plain(value):
    """Normalize a task-DB value (DictConfig / list / scalar) to primitives."""
    if OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


# ---------------------------------------------------------------------------
# Phase 1 — worker executes composite tasks
# ---------------------------------------------------------------------------

def test_composite_task_runs_stages_in_order(tmp_path):
    root = tmp_path / "xp1"
    task = {
        "_stages_": [
            _stage("a", root),
            _stage("b", root, upstream=str(root / "a")),
        ]
    }
    db_path = tmp_path / "run.lock.tasks.db"
    queue_tasks(db_path, [task])

    _run_worker(db_path)

    assert _read_order(root) == ["a", "b"]
    assert (root / "a" / "run.complete").exists()
    assert (root / "b" / "run.complete").exists()

    rows = get_all_tasks(db_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "done"
    # Per-stage result list, yaml-roundtripped through the DB.
    result = _plain(rows[0]["result"])
    assert [r["result"]["name"] for r in result] == ["a", "b"]
    assert result[0]["save_dir"] == str(root / "a")


def test_composite_stage_dirs_have_markers(tmp_path):
    root = tmp_path / "xp1"
    task = {"_stages_": [_stage("a", root), _stage("b", root)]}
    db_path = tmp_path / "run.lock.tasks.db"
    queue_tasks(db_path, [task])

    _run_worker(db_path)

    from flexlock.taskdb import _hash_task
    task_id = _hash_task(get_all_tasks(db_path)[0]["task"])
    for name in ("a", "b"):
        marker = root / name / ".flexlock_marker"
        assert marker.exists()
        payload = json.loads(marker.read_text())
        assert payload["task_id"] == task_id
        # Marker points at the shared DB (relative to the stage dir's parent
        # when possible, absolute otherwise).
        db_ref = Path(payload["db"])
        resolved = db_ref if db_ref.is_absolute() else (root / name).parent / db_ref
        assert resolved.resolve() == db_path.resolve()


def test_composite_failure_aborts_remaining_stages(tmp_path):
    root = tmp_path / "xp1"
    task = {
        "_stages_": [
            _stage("a", root),
            _stage("b", root, fail=True),
            _stage("c", root),
        ]
    }
    db_path = tmp_path / "run.lock.tasks.db"
    queue_tasks(db_path, [task])

    _run_worker(db_path)

    # Stage a completed; b failed; c never ran.
    assert _read_order(root) == ["a", "b"]
    assert (root / "a" / "run.complete").exists()
    assert not (root / "b" / "run.complete").exists()
    assert not (root / "c").exists()

    row = get_all_tasks(db_path)[0]
    assert row["status"] == "failed"
    assert row["error"].startswith("[stage 2/3 b]")
    assert "failed on purpose" in row["error"]

    # run.error sidecar in the failing stage dir carries the stage label.
    err = json.loads((root / "b" / "run.error").read_text())
    assert err["stage"] == "stage 2/3 b"


def test_composite_skip_complete_resumes_past_done_stages(tmp_path):
    root = tmp_path / "xp1"
    stage_a = _stage("a", root)
    stage_b = _stage("b", root)

    # Pre-complete stage a on disk (as a previous partial run would leave it).
    a_dir = Path(stage_a["save_dir"])
    a_dir.mkdir(parents=True)
    (a_dir / "run.complete").write_text(json.dumps({"ts": "x", "version": 1}))
    (a_dir / "results.json").write_text(json.dumps({"name": "a"}))

    task = {"_stages_": [stage_a, stage_b], "_skip_complete_": True}
    db_path = tmp_path / "run.lock.tasks.db"
    queue_tasks(db_path, [task])

    _run_worker(db_path)

    # Only b actually executed; a was skipped but its result was collected.
    assert _read_order(root) == ["b"]
    row = get_all_tasks(db_path)[0]
    assert row["status"] == "done"
    result = _plain(row["result"])
    assert result[0].get("skipped") is True
    assert result[0]["result"] == {"name": "a"}
    assert result[1]["result"]["name"] == "b"


def test_composite_without_skip_complete_reruns_all_stages(tmp_path):
    root = tmp_path / "xp1"
    stage_a = _stage("a", root)
    a_dir = Path(stage_a["save_dir"])
    a_dir.mkdir(parents=True)
    (a_dir / "run.complete").write_text(json.dumps({"ts": "x", "version": 1}))

    task = {"_stages_": [stage_a, _stage("b", root)]}
    db_path = tmp_path / "run.lock.tasks.db"
    queue_tasks(db_path, [task])

    _run_worker(db_path)

    # No _skip_complete_ → every stage runs (guard was applied driver-side).
    assert _read_order(root) == ["a", "b"]
    assert get_all_tasks(db_path)[0]["status"] == "done"


def test_plain_task_behaviour_unchanged(tmp_path):
    """A plain dict task keeps the exact single-config worker behaviour."""
    root = tmp_path / "sweep"
    task = _stage("a", root)
    db_path = tmp_path / "run.lock.tasks.db"
    queue_tasks(db_path, [task])

    _run_worker(db_path)

    assert _read_order(root) == ["a"]
    assert (root / "a" / "run.complete").exists()
    row = get_all_tasks(db_path)[0]
    assert row["status"] == "done"
    result = _plain(row["result"])
    assert result == {"name": "a"}
