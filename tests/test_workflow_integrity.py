"""Failure exits and output health across the existing execution entry points."""

import json
import subprocess
import sys
from pathlib import Path

import cloudpickle
import pytest
from omegaconf import OmegaConf

from flexlock.api import Project
from flexlock.exceptions import FlexLockValidationError, WorkerExecutionError
from flexlock.outputs import validate_outputs
from flexlock.taskdb import get_all_tasks, queue_tasks
from flexlock.worker import worker_loop


def produce(save_dir, fail=False, omit=False):
    if fail:
        raise RuntimeError("injected failure")
    if not omit:
        Path(save_dir, "predictions.json").write_text('[1, 2, 3]')
    return {"count": 3}


def validate_count(path, count):
    return len(json.loads(Path(path).read_text())) == count


def stage(root, **kwargs):
    return OmegaConf.create({
        "_target_": "tests.test_workflow_integrity.produce",
        "save_dir": str(root),
        "_snapshot_": {"repos": {}},
        "_outputs_": {"predictions": "predictions.json"},
        **kwargs,
    })


@pytest.fixture(autouse=True)
def fast_worker(monkeypatch):
    monkeypatch.setattr("flexlock.worker.time.sleep", lambda _: None)


def test_worker_drains_after_failure_and_persists_receipts(tmp_path):
    db = tmp_path / "tasks.db"
    queue_tasks(db, [
        {"_stages_": [OmegaConf.to_container(stage(tmp_path / "bad", fail=True))]},
        OmegaConf.to_container(stage(tmp_path / "good")),
    ])
    with pytest.raises(WorkerExecutionError, match="1 failed task"):
        worker_loop(None, OmegaConf.create({}), None, db)
    assert sorted(r["status"] for r in get_all_tasks(db)) == ["done", "failed"]
    assert (tmp_path / "good/run.complete").exists()
    assert "injected failure" in (tmp_path / "bad/run.error").read_text()


@pytest.mark.parametrize("backend", ["slurm", "pbs"])
def test_scheduler_bootstrap_exits_nonzero_on_failed_composite(tmp_path, backend):
    from flexlock.backends.slurm import SlurmBackend
    from flexlock.backends.pbs import PBSBackend

    db = tmp_path / "tasks.db"
    bad = OmegaConf.to_container(stage(tmp_path / "bad", fail=True))
    downstream = OmegaConf.to_container(stage(tmp_path / "downstream"))
    queue_tasks(db, [{"_stages_": [bad, downstream]}])
    payload = tmp_path / "task.pkl"
    payload.write_bytes(cloudpickle.dumps((worker_loop, (None, {}, None, db), {})))
    cls = SlurmBackend if backend == "slurm" else PBSBackend
    script = cls(tmp_path, startup_lines=[], python_exe=sys.executable).render_script(payload)
    completed = subprocess.run(["bash"], input=script, text=True, capture_output=True)
    assert completed.returncode != 0, completed.stderr
    assert get_all_tasks(db)[0]["status"] == "failed"
    assert not (tmp_path / "downstream").exists()


@pytest.mark.parametrize("n_jobs", [1, 2])
def test_worker_cli_failure_exits_nonzero(tmp_path, n_jobs):
    db = tmp_path / "tasks.db"
    queue_tasks(db, [OmegaConf.to_container(stage(tmp_path / "bad", fail=True))])
    result = subprocess.run(
        [sys.executable, "-m", "flexlock.worker_cli", "--task-db", str(db),
         "--n-jobs", str(n_jobs)], capture_output=True, text=True,
    )
    assert result.returncode != 0, result.stderr
    assert get_all_tasks(db)[0]["status"] == "failed"


def test_pipeline_cli_failure_and_resume(tmp_path):
    cfg = tmp_path / "pipeline.yaml"
    cfg.write_text(OmegaConf.to_yaml(OmegaConf.create({
        "first": stage(tmp_path / "first"),
        "bad": stage(tmp_path / "bad", fail=True),
        "last": stage(tmp_path / "last"),
    })))
    command = [sys.executable, "-m", "flexlock.run_cli", "-c", str(cfg),
               "-s", "first", "bad", "last"]
    failure = subprocess.run(command, capture_output=True, text=True)
    assert failure.returncode != 0, failure.stderr
    assert (tmp_path / "first/run.complete").exists()
    assert not (tmp_path / "last").exists()
    # Fix the injected failure; legacy skip resumes the healthy first stage.
    plan = OmegaConf.load(cfg)
    plan.bad.fail = False
    cfg.write_text(OmegaConf.to_yaml(plan))
    before = (tmp_path / "first/run.complete").read_bytes()
    success = subprocess.run(command + ["--save-dir-policy", "skip"], capture_output=True, text=True)
    assert success.returncode == 0, success.stderr
    assert (tmp_path / "first/run.complete").read_bytes() == before
    assert (tmp_path / "last/run.complete").exists()


@pytest.mark.parametrize("mode", ["skip", "smart", "pipeline", "serial", "parallel"])
def test_deleted_output_rejects_reuse(tmp_path, mode):
    cfg = stage(tmp_path / "run")
    proj = Project()
    sweep = [{}, {"save_dir": str(tmp_path / "other")}]
    if mode == "pipeline":
        proj.submit_pipeline([[cfg]])
    elif mode in ("serial", "parallel"):
        proj.submit(cfg, sweep=sweep, n_jobs=2 if mode == "parallel" else 1, smart_run=False)
    else:
        proj.submit(cfg, smart_run=False)
    Path(cfg.save_dir, "predictions.json").unlink()
    with pytest.raises(FlexLockValidationError, match="required path is missing"):
        if mode == "pipeline":
            proj.submit_pipeline([[cfg]], save_dir_policy="skip")
        elif mode in ("serial", "parallel"):
            proj.submit(cfg, sweep=sweep, n_jobs=2 if mode == "parallel" else 1,
                        smart_run=False, save_dir_policy="skip")
        elif mode == "smart":
            proj.submit(cfg, smart_run=True, search_dirs=[str(tmp_path)])
        else:
            proj.submit(cfg, smart_run=False, save_dir_policy="skip")


def test_missing_output_fails_completion(tmp_path):
    cfg = stage(tmp_path / "run", omit=True)
    with pytest.raises(FlexLockValidationError, match="required path is missing"):
        Project().submit(cfg, smart_run=False)
    assert not Path(cfg.save_dir, "run.complete").exists()
    assert Path(cfg.save_dir, "run.error").exists()


@pytest.mark.parametrize("pipeline", [False, True])
def test_generated_results_can_be_a_required_output(tmp_path, pipeline):
    cfg = stage(tmp_path / "run", _outputs_=["results.json"])
    if pipeline:
        assert Project().submit_pipeline([[cfg]])[0][0].status == "SUCCESS"
    else:
        assert Project().submit(cfg, smart_run=False).status == "SUCCESS"
    validate_outputs(cfg)


def test_checksum_and_count_validator(tmp_path):
    cfg = stage(tmp_path / "run", _outputs_={"predictions": {
        "path": "predictions.json", "sha256": True,
        "validator": {"_target_": "tests.test_workflow_integrity.validate_count", "count": 3},
    }})
    Project().submit(cfg, smart_run=False)
    validate_outputs(cfg)
    Path(cfg.save_dir, "predictions.json").write_text('[1, 2, 4]')
    with pytest.raises(FlexLockValidationError, match="SHA256 differs"):
        validate_outputs(cfg)
    cfg._outputs_.predictions.sha256 = False
    Path(cfg.save_dir, "predictions.json").write_text('[1]')
    with pytest.raises(FlexLockValidationError, match="validator returned False"):
        validate_outputs(cfg)


def test_cache_rebases_outputs_to_candidate_directory(tmp_path):
    cfg = stage(tmp_path / "old", _outputs_=["${save_dir}/predictions.json"])
    Project().submit(cfg, smart_run=False)
    cfg.save_dir = str(tmp_path / "new")
    result = Project().submit(cfg, smart_run=True, search_dirs=[str(tmp_path)])
    assert result.status == "CACHED"
    assert result.save_dir == str(tmp_path / "old")
    assert not (tmp_path / "new").exists()


def test_worker_rejects_corrupt_completed_stage(tmp_path):
    cfg = stage(tmp_path / "done")
    Project().submit(cfg, smart_run=False)
    Path(cfg.save_dir, "predictions.json").unlink()
    db = tmp_path / "tasks.db"
    queue_tasks(db, [{"_stages_": [OmegaConf.to_container(cfg)], "_skip_complete_": True}])
    with pytest.raises(WorkerExecutionError):
        worker_loop(None, {}, None, db)
    assert get_all_tasks(db)[0]["status"] == "failed"
    assert not Path(cfg.save_dir, "run.complete").exists()


def test_done_task_db_validates_outputs_without_resubmitting(tmp_path):
    from flexlock.parallel import ParallelExecutor
    from flexlock.utils import instantiate

    cfg = stage(tmp_path / "run")
    task = OmegaConf.to_container(cfg)
    executor = ParallelExecutor(instantiate, [task], None, OmegaConf.create({"save_dir": str(tmp_path)}), n_jobs=1)
    assert executor.run()
    Path(cfg.save_dir, "predictions.json").unlink()
    with pytest.raises(FlexLockValidationError, match="required path is missing"):
        executor.run()
