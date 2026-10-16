"""Integration tests: collision-guard save_dir_policy through Project.submit.

Configs keep a stable save_dir; the policy decides what happens when that
directory already holds a run (run.lock present). Default: raise.
"""

from pathlib import Path

import pytest
from omegaconf import OmegaConf

from flexlock.api import Project
from flexlock.exceptions import FlexLockValidationError

CALLS_FILE = "calls.txt"


def guard_stage(value=0, save_dir=None):
    """Record each execution so tests can count actual runs."""
    calls = Path(save_dir) / CALLS_FILE
    n = int(calls.read_text()) + 1 if calls.exists() else 1
    calls.write_text(str(n))
    return {"value": value}


def _n_calls(save_dir):
    calls = Path(save_dir) / CALLS_FILE
    return int(calls.read_text()) if calls.exists() else 0


@pytest.fixture
def proj(tmp_path):
    defaults = tmp_path / "defaults.py"
    defaults.write_text(
        "defaults = {'stage': {'_target_': 'tests.test_save_dir_guard.guard_stage',"
        " 'value': 1}}\n"
    )
    return Project(defaults=f"{defaults}:defaults")


def _cfg(proj, tmp_path, **kw):
    cfg = OmegaConf.create(proj.get("stage"))
    cfg.save_dir = str(tmp_path / "run")
    for k, v in kw.items():
        cfg[k] = v
    return cfg


def test_default_runs_fresh_then_raises_on_rerun(proj, tmp_path):
    cfg = _cfg(proj, tmp_path)
    proj.submit(cfg)
    assert _n_calls(cfg.save_dir) == 1
    with pytest.raises(FlexLockValidationError, match="already contains"):
        proj.submit(_cfg(proj, tmp_path))
    assert _n_calls(cfg.save_dir) == 1




def test_force_reruns_in_place(proj, tmp_path):
    cfg = _cfg(proj, tmp_path)
    proj.submit(cfg)
    proj.submit(_cfg(proj, tmp_path),  force=True)
    assert _n_calls(cfg.save_dir) == 2


def test_unsafe_reruns_in_place(proj, tmp_path):
    cfg = _cfg(proj, tmp_path)
    proj.submit(cfg)
    proj.submit(_cfg(proj, tmp_path),  save_dir_policy="unsafe")
    assert _n_calls(cfg.save_dir) == 2


def test_overwrite_cleans_then_reruns(proj, tmp_path):
    cfg = _cfg(proj, tmp_path)
    proj.submit(cfg)
    stale = Path(cfg.save_dir) / "stale.txt"
    stale.write_text("old")
    proj.submit(_cfg(proj, tmp_path),  save_dir_policy="overwrite")
    assert not stale.exists()
    # Counter was wiped with the dir, so a fresh run counts 1 again.
    assert _n_calls(cfg.save_dir) == 1


def test_skip_returns_cached_without_executing(proj, tmp_path):
    cfg = _cfg(proj, tmp_path)
    proj.submit(cfg)
    r = proj.submit(_cfg(proj, tmp_path),  save_dir_policy="skip")
    assert r.status == "CACHED"
    assert r.save_dir == cfg.save_dir
    assert _n_calls(cfg.save_dir) == 1


def test_skip_raises_on_incomplete_run(proj, tmp_path):
    cfg = _cfg(proj, tmp_path)
    proj.submit(cfg)
    (Path(cfg.save_dir) / "run.complete").unlink()  # simulate a crashed run
    with pytest.raises(FlexLockValidationError, match="incomplete"):
        proj.submit(_cfg(proj, tmp_path),  save_dir_policy="skip")




def test_increment_versions_on_config_change(proj, tmp_path):
    cfg = _cfg(proj, tmp_path)
    proj.submit(cfg, save_dir_policy="increment")
    cfg2 = _cfg(proj, tmp_path, value=2)
    proj.submit(cfg2, save_dir_policy="increment")
    assert (tmp_path / "run_0000").is_dir()
    assert (tmp_path / "run_0001").is_dir()


def test_serial_sweep_continues_queue_but_explicit_skip_requires_completion(proj, tmp_path):
    sweep = [{"value": 1}, {"value": 2}]
    cfg = _cfg(proj, tmp_path)
    proj.submit(cfg, sweep=sweep, sweep_dir_suffix=True)
    item0 = tmp_path / "run" / "sweep_0000"
    item1 = tmp_path / "run" / "sweep_0001"
    assert _n_calls(item0) == 1 and _n_calls(item1) == 1

    # The same recorded task payload continues its queue; it does not run again.
    continued = proj.submit(_cfg(proj, tmp_path), sweep=sweep, sweep_dir_suffix=True)
    assert [r.status for r in continued] == ['SUCCESS', 'SUCCESS']
    selected = proj.submit(_cfg(proj, tmp_path), sweep=sweep, sweep_dir_suffix=True,
                           save_dir_policy='skip')
    assert [r.status for r in selected] == ['CACHED', 'CACHED']

    # Incomplete reuse is not authorization to rerun a crashed item in place.
    (item1 / "run.complete").unlink()
    with pytest.raises(FlexLockValidationError, match='incomplete item'):
        proj.submit(_cfg(proj, tmp_path), sweep=sweep, sweep_dir_suffix=True,
                    save_dir_policy='skip')
    assert _n_calls(item0) == 1
    assert _n_calls(item1) == 1
