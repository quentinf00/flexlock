"""Tests for the run.complete marker (Spec D).

A run is a cache hit only when both run.lock and run.complete are present.
Interrupted runs leave run.lock without run.complete and must not match.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from omegaconf import OmegaConf

from flexlock.snapshot import RunTracker, write_complete_marker, is_complete


# --- Primitives ---

def test_write_complete_marker_atomic(tmp_path):
    """write_complete_marker creates run.complete with a timestamp payload."""
    marker = write_complete_marker(tmp_path)
    assert marker.name == "run.complete"
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert "ts" in payload
    assert payload["version"] == 1


@pytest.mark.parametrize("umask, mode", [(0o022, 0o644), (0o002, 0o664), (0o077, 0o600)])
def test_run_record_files_honor_umask(tmp_path, umask, mode):
    from flexlock.run_record import RunRecord

    old_umask = os.umask(umask)
    try:
        record = RunRecord(tmp_path)
        paths = [record.write_lock({"config": {}}), record.mark_complete()]
    finally:
        os.umask(old_umask)
    assert all(path.stat().st_mode & 0o777 == mode for path in paths)


def test_sweep_marker_tracks_all_tags_and_is_invalidated_on_append(tmp_path):
    from flexlock.run_record import RunRecord
    from flexlock.taskdb import (finish_task, publish_sweep_completion, queue_tasks)

    record = RunRecord(tmp_path)
    record.write_lock({"config": {}})
    db = tmp_path / "run.lock.tasks.db"
    first, second, third = {"x": 1}, {"x": 2}, {"x": 3}
    queue_tasks(db, [first], tag="first")
    queue_tasks(db, [second], tag="second")
    finish_task(db, first)
    publish_sweep_completion(db)
    assert not record.is_complete
    finish_task(db, second)
    publish_sweep_completion(db)
    assert record.is_complete

    queue_tasks(db, [first], tag="first")
    assert record.is_complete
    queue_tasks(db, [third], tag="third")
    assert not record.is_complete
    finish_task(db, third, error="missing output")
    publish_sweep_completion(db)
    assert not record.is_complete


def test_is_complete_requires_both_files(tmp_path):
    assert not is_complete(tmp_path)  # nothing
    (tmp_path / "run.lock").write_text("config: {}")
    assert not is_complete(tmp_path)  # lock only
    (tmp_path / "run.complete").write_text("{}")
    assert is_complete(tmp_path)  # both


def test_marker_overwrites_existing(tmp_path):
    """Re-running into the same dir replaces the marker (no append/lock issue)."""
    write_complete_marker(tmp_path)
    first = json.loads((tmp_path / "run.complete").read_text())["ts"]
    import time

    time.sleep(0.01)
    write_complete_marker(tmp_path)
    second = json.loads((tmp_path / "run.complete").read_text())["ts"]
    assert first != second


# --- RunTracker integration ---

def test_run_tracker_save_then_mark_complete(tmp_path):
    """RunTracker.save writes run.lock; mark_complete writes run.complete next to it."""
    cfg = OmegaConf.create({"save_dir": str(tmp_path), "param": 1})
    tracker = RunTracker(save_dir=tmp_path)
    with patch("flexlock.snapshot.create_shadow_snapshot"):
        tracker.save(cfg)
    assert (tmp_path / "run.lock").exists()
    assert not (tmp_path / "run.complete").exists()
    tracker.mark_complete(result={"x": 1})
    assert (tmp_path / "run.complete").exists()
    assert is_complete(tmp_path)


def test_run_tracker_mark_complete_after_save_dir_resolve(tmp_path):
    """RunTracker.save resolves save_dir from the snapshot config; mark_complete
    then writes to the same resolved dir even when the RunTracker was constructed
    with a different (template) path."""
    resolved_dir = tmp_path / "run_0001"
    cfg = OmegaConf.create({"save_dir": str(resolved_dir), "param": 1})
    # Construct tracker with the TEMPLATE dir (different from resolved)
    tracker = RunTracker(save_dir=tmp_path / "template")
    with patch("flexlock.snapshot.create_shadow_snapshot"):
        tracker.save(cfg)
    tracker.mark_complete()
    assert (resolved_dir / "run.lock").exists()
    assert (resolved_dir / "run.complete").exists()
    # Template dir should not have the lock or marker
    assert not (tmp_path / "template" / "run.complete").exists()


# --- _find_matching_run integration ---

def _make_run_dir(path: Path, fingerprint: dict, complete: bool):
    path.mkdir(parents=True, exist_ok=True)
    (path / "run.lock").write_text(yaml.safe_dump(fingerprint))
    if complete:
        write_complete_marker(path)






# --- force=True semantics ---

def test_force_invalidates_only_marker(tmp_path):
    """force=True removes run.complete but keeps run.lock and other outputs."""
    from flexlock.api import Project

    save_dir = tmp_path / "run"
    save_dir.mkdir()
    (save_dir / "run.lock").write_text("config: {}")
    (save_dir / "run.complete").write_text("{}")
    (save_dir / "results.json").write_text('{"x": 1}')
    (save_dir / "model.pt").write_text("fake-weights")

    proj = Project.__new__(Project)
    proj.defaults = OmegaConf.create({})

    cfg = OmegaConf.create({"save_dir": str(save_dir)})
    # Drive only the force branch — submit short-circuits to local exec, mock it.
    with patch("flexlock.api.snapshot"), patch(
        "flexlock.api.extract_tracking_info", return_value=({}, {}, None)
    ), patch("flexlock.api.instantiate", return_value={"x": 1}):
        proj.submit(cfg, force=True,  wait=True)

    assert (save_dir / "run.lock").exists(), "run.lock must be preserved"
    assert (save_dir / "model.pt").exists(), "outputs must be preserved"
    # After successful re-run, run.complete is written again
    assert (save_dir / "run.complete").exists()
