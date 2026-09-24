"""A single-task HPC/isolated submission must leave a full run.lock.

Regression: the ParallelExecutor wrapper wrote a placeholder master run.lock
({save_dir, _snapshot_}) and the worker stored the real snapshot only in
run.lock.tasks.db, so ${run_lock:...}, flexlock show/diff and
``flexlock-run -c run.lock`` saw an empty config.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from omegaconf import OmegaConf

from flexlock import Project
from flexlock.resolvers import run_lock_resolver
from flexlock.run_record import (
    is_placeholder_lock,
    load_lock_data,
    materialize_lock,
)


def stage(save_dir=None, lr=1e-3, datamodule=None, run_dir=None):
    return {"lr": lr, "stats": (datamodule or {}).get("stats_file")}


class _Job:
    job_id = "4242"


class FakeSlurmBackend:
    """Runs worker_loop synchronously in-process, like the Slurm job would."""

    def __init__(self, folder, **kw):
        self.folder = Path(folder)

    def submit(self, fn, *args):
        fn(*args)
        return _Job()

    def is_terminal(self, job_id):
        return True


@pytest.fixture(autouse=True)
def _no_stagger(monkeypatch):
    monkeypatch.setattr("flexlock.worker.time.sleep", lambda *_: None)


def _cfg(save_dir, **extra):
    return OmegaConf.create(
        {
            "_target_": "tests.test_single_task_runlock.stage",
            "save_dir": str(save_dir),
            "lr": 5e-4,
            "datamodule": {"stats_file": "/data/stats.json"},
            **extra,
        }
    )


def _submit_hpc(cfg, tmp_path, **kw):
    slurm_yaml = tmp_path / "slurm.yaml"
    slurm_yaml.write_text("partition: fake\n")
    with patch("flexlock.parallel.SlurmBackend", FakeSlurmBackend):
        return Project().submit(cfg, slurm_config=str(slurm_yaml), smart_run=False, **kw)


def _lock(d):
    return yaml.safe_load((Path(d) / "run.lock").read_text())


@pytest.mark.parametrize("mode", ["slurm", "isolated"])
def test_single_task_writes_full_run_lock(tmp_path, mode):
    save_dir = tmp_path / "up"
    cfg = _cfg(save_dir)
    if mode == "slurm":
        _submit_hpc(cfg, tmp_path, note="why")
    else:
        Project().submit(cfg, isolated=True, smart_run=False, note="why")

    lock = _lock(save_dir)
    assert not is_placeholder_lock(lock)
    assert lock["config"]["_target_"].endswith(".stage")
    assert lock["config"]["datamodule"]["stats_file"] == "/data/stats.json"
    assert lock["note"] == "why"
    assert "parent" not in lock  # no self-reference
    assert lock.get("fingerprint")
    assert (save_dir / "run.complete").exists()
    assert run_lock_resolver(str(save_dir), "config.lr") == 5e-4
    # run.lock.tasks refreshed by the worker, not left at "[]"
    assert "status: done" in (save_dir / "run.lock.tasks").read_text()


def test_downstream_run_lock_resolver_after_hpc(tmp_path):
    up = tmp_path / "up"
    _submit_hpc(_cfg(up), tmp_path)
    down = OmegaConf.create(
        {
            "_target_": "tests.test_single_task_runlock.stage",
            "run_dir": str(up),
            "save_dir": str(tmp_path / "down"),
            "datamodule": {
                "stats_file": "${run_lock:${run_dir},config.datamodule.stats_file}"
            },
        }
    )
    assert Project().submit(down, smart_run=False).result["stats"] == "/data/stats.json"


def test_owner_records_repos_and_survives_git_failure(tmp_path, monkeypatch):
    fake_repos = {"main": {"path": str(tmp_path)}}
    monkeypatch.setattr(
        "flexlock.worker.extract_tracking_info", lambda cfg: (fake_repos, {}, [])
    )
    snap_mod = sys.modules["flexlock.snapshot"]  # name shadowed by flexlock.snapshot()
    monkeypatch.setattr(
        snap_mod, "create_shadow_snapshot",
        lambda path, ref_name=None: {"commit": "c0ffee", "tree": "t", "is_dirty": False},
    )
    monkeypatch.setattr("flexlock.worker.compute_fingerprint", lambda *a, **k: "fp")
    _submit_hpc(_cfg(tmp_path / "a"), tmp_path)
    assert _lock(tmp_path / "a")["repos"]["main"]["commit"] == "c0ffee"

    def boom(*a, **k):
        raise RuntimeError("no git on compute node")

    monkeypatch.setattr(snap_mod, "create_shadow_snapshot", boom)
    _submit_hpc(_cfg(tmp_path / "b"), tmp_path)
    lock_b = _lock(tmp_path / "b")
    assert lock_b["config"]["lr"] == 5e-4  # task still ran, full config written
    assert (tmp_path / "b" / "run.complete").exists()


def test_sweep_master_keeps_placeholder_and_items_have_no_lock(tmp_path):
    root = tmp_path / "sweep"
    cfg = _cfg(root / "item")
    slurm_yaml = tmp_path / "slurm.yaml"
    slurm_yaml.write_text("partition: fake\n")
    with patch("flexlock.parallel.SlurmBackend", FakeSlurmBackend):
        Project().submit(
            cfg,
            sweep=[{"lr": 1.0}, {"lr": 2.0}],
            sweep_dir_suffix=True,
            slurm_config=str(slurm_yaml),
            smart_run=False,
        )
    master = root / "item"
    assert is_placeholder_lock(_lock(master))  # N tasks → no single config
    assert load_lock_data(master)["config"].keys() <= {"save_dir", "_snapshot_"}
    for i in range(2):
        item = master / f"sweep_{i:04d}"
        assert not (item / "run.lock").exists()
        assert (item / ".flexlock_marker").exists()


def _make_legacy_placeholder(run_dir: Path):
    """Rewrite a fixed run dir back into the pre-fix on-disk shape."""
    (run_dir / "run.lock").write_text(
        yaml.safe_dump(
            {"timestamp": "t", "note": "n",
             "config": {"save_dir": str(run_dir), "_snapshot_": {}}}
        )
    )


def test_readers_fall_back_to_task_db_for_legacy_placeholder(tmp_path):
    up = tmp_path / "up"
    _submit_hpc(_cfg(up), tmp_path)
    _make_legacy_placeholder(up)

    assert run_lock_resolver(str(up), "config.datamodule.stats_file") == "/data/stats.json"
    eff = load_lock_data(up)
    assert eff["note"] == "n" and eff["config"]["lr"] == 5e-4

    from flexlock import query
    from flexlock.diff_cli import load_snapshot_from_dir

    assert query.load_run_summary(up, downstream=False)["target"].endswith(".stage")
    assert load_snapshot_from_dir(up)["config"]["lr"] == 5e-4

    # marker missing → match by snapshot config.save_dir
    (up / ".flexlock_marker").unlink()
    assert load_lock_data(up)["config"]["lr"] == 5e-4

    assert materialize_lock(up) is True
    assert (up / "run.lock.placeholder.bak").exists()
    assert _lock(up)["config"]["lr"] == 5e-4
    assert materialize_lock(up) is False  # idempotent


def test_rerun_from_legacy_placeholder_lock(tmp_path):
    from flexlock.runner import FlexLockRunner

    up = tmp_path / "up"
    _submit_hpc(_cfg(up), tmp_path)
    _make_legacy_placeholder(up)
    out = FlexLockRunner().run(
        ["-c", str(up / "run.lock"), "-s", "config",
         "-o", f"config.save_dir={tmp_path / 'rerun'}"]
    )
    assert out == {"lr": 5e-4, "stats": "/data/stats.json"}


def test_repair_locks_cli(tmp_path, capsys):
    from flexlock.cli import main as cli_main

    up = tmp_path / "res" / "up"
    _submit_hpc(_cfg(up), tmp_path)
    _make_legacy_placeholder(up)

    with patch.object(sys, "argv", ["flexlock", "repair-locks", str(tmp_path / "res"), "-n"]):
        cli_main()
    assert is_placeholder_lock(_lock(up))  # dry run writes nothing
    assert str(up) in capsys.readouterr().out

    with patch.object(sys, "argv", ["flexlock", "repair-locks", str(tmp_path / "res")]):
        cli_main()
    assert _lock(up)["config"]["lr"] == 5e-4
    assert (up / "run.lock.placeholder.bak").exists()


def _counting_stage(tick_file=None, save_dir=None):
    with open(tick_file, "a") as f:
        f.write("1")
    return {"n": len(Path(tick_file).read_text())}


@pytest.mark.parametrize("mode", ["slurm", "isolated"])
def test_force_reruns_single_task_submission(tmp_path, mode):
    """force=True on a single HPC/isolated submit must re-execute the task.

    Regression: force deleted run.complete, but the executor re-queued the
    task with INSERT OR IGNORE, found the old 'done' row and ran nothing.
    """
    tick = tmp_path / "ticks.txt"
    save_dir = tmp_path / "run"
    cfg = OmegaConf.create(
        {
            "_target_": "tests.test_single_task_runlock._counting_stage",
            "tick_file": str(tick),
            "save_dir": str(save_dir),
        }
    )

    def submit(**kw):
        if mode == "slurm":
            return _submit_hpc(cfg.copy(), tmp_path, **kw)
        return Project().submit(cfg.copy(), isolated=True, smart_run=False, **kw)

    submit()
    assert tick.read_text() == "1"
    submit(force=True)
    assert tick.read_text() == "11"
    assert (save_dir / "run.complete").exists()
    assert json.loads((save_dir / "results.json").read_text()) == {"n": 2}
