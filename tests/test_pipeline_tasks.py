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


# ---------------------------------------------------------------------------
# Phase 2 — Project.submit_pipeline
# ---------------------------------------------------------------------------

def _item(root, names=("train", "probe")):
    """Build one pipeline item: a list of frozen stage DictConfigs."""
    cfgs = []
    prev = None
    for name in names:
        d = _stage(name, root)
        if prev is not None:
            d["upstream"] = prev
        prev = d["save_dir"]
        cfgs.append(OmegaConf.create(d))
    return cfgs


def test_submit_pipeline_local_single_item(tmp_path):
    from flexlock.api import Project

    root = tmp_path / "xp1"
    results = Project().submit_pipeline([_item(root)])

    assert len(results) == 1 and len(results[0]) == 2
    assert all(r.status == "SUCCESS" for r in results[0])
    assert _read_order(root) == ["train", "probe"]
    assert results[0][0].result == {"name": "train"}
    # Task DB lives at the item's pipeline dir (master root).
    assert (root / "run.lock.tasks.db").exists()


def test_submit_pipeline_two_items_parallel(tmp_path):
    """2 items x 2 stages, n_jobs=2: intra-item order holds, items fan out."""
    from flexlock.api import Project

    base = tmp_path / "results"
    items = [_item(base / "xp1"), _item(base / "xp2")]
    results = Project().submit_pipeline(items, n_jobs=2)

    assert len(results) == 2
    for item_res, root in zip(results, (base / "xp1", base / "xp2")):
        assert [r.status for r in item_res] == ["SUCCESS", "SUCCESS"]
        # per-item log: intra-item ordering preserved
        assert _read_order(root) == ["train", "probe"]
    # Master root = common parent of the item pipeline dirs.
    assert (base / "run.lock.tasks.db").exists()


def test_submit_pipeline_containment_validation(tmp_path):
    from flexlock.api import Project
    from flexlock.exceptions import FlexLockValidationError

    items = [_item(tmp_path / "a" / "xp1"), _item(tmp_path / "b" / "xp2")]
    with pytest.raises(FlexLockValidationError, match="sweep-root"):
        Project().submit_pipeline(items)

    # Explicit sweep_root opts out of the containment constraint.
    results = Project().submit_pipeline(items, sweep_root=str(tmp_path))
    assert len(results) == 2
    assert (tmp_path / "run.lock.tasks.db").exists()


def test_submit_pipeline_rejects_naming_policies(tmp_path):
    from flexlock.api import Project
    from flexlock.exceptions import FlexLockValidationError

    for policy in ("increment", "timestamp"):
        with pytest.raises(FlexLockValidationError, match="not supported"):
            Project().submit_pipeline(
                [_item(tmp_path / "xp1")], save_dir_policy=policy
            )


def test_submit_pipeline_guard_raises_on_occupied(tmp_path):
    from flexlock.api import Project
    from flexlock.exceptions import FlexLockValidationError

    root = tmp_path / "xp1"
    item = _item(root)
    # Occupy the first stage dir with a previous run.lock.
    d = Path(item[0].save_dir)
    d.mkdir(parents=True)
    (d / "run.lock").write_text("config: {}\n")

    with pytest.raises(FlexLockValidationError, match="already contains"):
        Project().submit_pipeline([item])

    # 'overwrite' cleans the dir and proceeds.
    results = Project().submit_pipeline([item], save_dir_policy="overwrite")
    assert [r.status for r in results[0]] == ["SUCCESS", "SUCCESS"]


def test_submit_pipeline_force_resets_and_reruns(tmp_path):
    from flexlock.api import Project

    root = tmp_path / "xp1"
    item = _item(root)
    proj = Project()
    proj.submit_pipeline([item])
    assert _read_order(root) == ["train", "probe"]

    # Second run without force resumes via the DB (nothing new executes) —
    # with force everything reruns.
    proj.submit_pipeline([item], force=True)
    assert _read_order(root) == ["train", "probe", "train", "probe"]


def test_submit_pipeline_failure_result_shape(tmp_path):
    from flexlock.api import Project

    root = tmp_path / "xp1"
    fail_stage = OmegaConf.create(_stage("mid", root, fail=True))
    item = [
        OmegaConf.create(_stage("first", root)),
        fail_stage,
        OmegaConf.create(_stage("last", root)),
    ]
    results = Project().submit_pipeline([item])

    statuses = [r.status for r in results[0]]
    assert statuses == ["SUCCESS", "FAILED", "SUBMITTED"]
    assert "[stage 2/3 mid]" in results[0][1].error


def test_submit_pipeline_wait_false_returns_submitted(tmp_path):
    from unittest.mock import patch
    from flexlock.api import Project

    root = tmp_path / "xp1"
    with patch("flexlock.parallel.SlurmBackend") as mock_backend:
        mock_backend.return_value.submit.return_value.job_id = "123"
        slurm_yaml = tmp_path / "slurm.yaml"
        slurm_yaml.write_text("partition: test\n")
        results = Project().submit_pipeline(
            [_item(root)], slurm_config=str(slurm_yaml), wait=False
        )

    assert [r.status for r in results[0]] == ["SUBMITTED", "SUBMITTED"]


def test_submit_pipeline_dry_run_does_not_touch_db(tmp_path, capsys):
    from flexlock.api import Project

    root = tmp_path / "xp1"
    slurm_yaml = tmp_path / "slurm.yaml"
    slurm_yaml.write_text(yaml.safe_dump(
        {"startup_lines": ["#SBATCH --partition=test"], "python_exe": "python"}
    ))

    out = Project().submit_pipeline(
        [_item(root)], slurm_config=str(slurm_yaml), dry_run=True
    )

    assert out is None
    assert not (root / "run.lock.tasks.db").exists()
    assert "dry run" in capsys.readouterr().out


def test_submit_pipeline_smart_run_all_cached(tmp_path):
    from flexlock.api import Project

    root = tmp_path / "xp1"
    item = _item(root)
    proj = Project()
    proj.submit_pipeline([item])

    # Re-submit with smart_run: every stage cache-hits -> CACHED, no rerun.
    results = proj.submit_pipeline(
        [item], smart_run=True, search_dirs=[str(root)]
    )
    assert [r.status for r in results[0]] == ["CACHED", "CACHED"]
    assert _read_order(root) == ["train", "probe"]


# ---------------------------------------------------------------------------
# Phase 4 — composite entries in --sweep-file (dequeue)
# ---------------------------------------------------------------------------

_PIPELINE_YAML = """
pipeline_dir: ???

stage_a:
  _target_: tests.test_pipeline_tasks.record_stage
  name: a
  save_dir: ${pipeline_dir}/a
  log: ${pipeline_dir}/order.log

stage_b:
  _target_: tests.test_pipeline_tasks.record_stage
  name: b
  save_dir: ${pipeline_dir}/b
  log: ${pipeline_dir}/order.log
  upstream: ${pipeline_dir}/a
"""


def test_enqueue_then_sweep_file_roundtrip(tmp_path):
    """`-s a b --enqueue` twice → 2 composite entries; --sweep-file runs both."""
    from flexlock.runner import FlexLockRunner

    cfg_file = tmp_path / "pipeline.yaml"
    cfg_file.write_text(_PIPELINE_YAML)
    q = tmp_path / "queue.yaml"

    root1 = tmp_path / "xp1"
    root2 = tmp_path / "xp2"
    for root in (root1, root2):
        FlexLockRunner().run(cli_args=[
            "-c", str(cfg_file), "-s", "stage_a", "stage_b",
            "-o", f"pipeline_dir={root}", "--enqueue", str(q),
        ])

    # Deferred/root refs survived the roundtrip as concrete frozen values.
    queued = yaml.safe_load(q.read_text())
    assert len(queued) == 2
    assert queued[0]["_stages_"][0]["save_dir"] == str(root1 / "a")

    # Dequeue and run both composite items (no base re-merge).
    FlexLockRunner().run(cli_args=[
        "-c", str(cfg_file), "--sweep-file", str(q), "--n_jobs", "2",
    ])

    for root in (root1, root2):
        assert _read_order(root) == ["a", "b"]
        assert (root / "a" / "run.complete").exists()
        assert (root / "b" / "run.complete").exists()


def test_mixed_queue_plain_and_composite(tmp_path):
    """A queue with one plain override dict + one composite runs both."""
    from flexlock.runner import FlexLockRunner

    # Base config is a single-stage node; the plain item is an override for it.
    base = tmp_path / "base.yaml"
    plain_dir = tmp_path / "plain"
    base.write_text(yaml.safe_dump({
        "_target_": TARGET,
        "name": "plain",
        "save_dir": str(plain_dir),
        "log": str(plain_dir / "order.log"),
    }))

    comp_root = tmp_path / "comp"
    q = tmp_path / "queue.yaml"
    # Plain override entry.
    from flexlock import enqueue_to_file
    enqueue_to_file(q, {"name": "plain"})
    # Composite entry (two stages).
    enqueue_to_file(q, {"_stages_": [
        _stage("a", comp_root),
        _stage("b", comp_root, upstream=str(comp_root / "a")),
    ]})

    FlexLockRunner().run(cli_args=[
        "-c", str(base), "--sweep-file", str(q),
        "--sweep-root", str(tmp_path),
    ])

    assert _read_order(plain_dir) == ["plain"]
    assert _read_order(comp_root) == ["a", "b"]


# ---------------------------------------------------------------------------
# Phase 5 — single-stage --sweep + --enqueue
# ---------------------------------------------------------------------------

def test_single_stage_sweep_enqueue_writes_merged_items(tmp_path):
    """`--sweep 0.1,0.2 --sweep-target lr --enqueue q` → 2 merged plain entries."""
    from flexlock.runner import FlexLockRunner

    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.safe_dump({
        "_target_": "builtins.dict",
        "save_dir": str(tmp_path / "out"),
        "lr": 0.0,
        # A deferred resolver must survive the roundtrip unresolved.
        "ckpt": "${latest:model.ckpt}",
    }))
    q = tmp_path / "queue.yaml"

    FlexLockRunner().run(cli_args=[
        "-c", str(cfg_file),
        "--sweep", "0.1,0.2", "--sweep-target", "lr",
        "--enqueue", str(q),
    ])

    data = yaml.safe_load(q.read_text())
    assert len(data) == 2
    assert [d["lr"] for d in data] == [0.1, 0.2]
    assert "_stages_" not in data[0]
    # Deferred resolver preserved as a call string, not fired.
    assert data[0]["ckpt"] == "${latest:model.ckpt}"


def test_single_stage_enqueue_no_sweep_unchanged(tmp_path):
    """Without a sweep, --enqueue still writes exactly one compiled entry."""
    from flexlock.runner import FlexLockRunner

    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.safe_dump(
        {"_target_": "builtins.dict", "save_dir": "out", "lr": 0.01}
    ))
    q = tmp_path / "queue.yaml"

    FlexLockRunner().run(cli_args=["-c", str(cfg_file), "--enqueue", str(q)])

    data = yaml.safe_load(q.read_text())
    assert len(data) == 1
    assert data[0]["lr"] == 0.01
