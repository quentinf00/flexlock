"""Tests for flexlock.save_dir — explicit save_dir naming policies (Phase 1)."""

import multiprocessing as mp
from pathlib import Path

import pytest
from omegaconf import OmegaConf

from flexlock.save_dir import apply_save_dir_policy, next_versioned_path


def test_next_versioned_path_basic(tmp_path):
    base = tmp_path / "run"
    assert next_versioned_path(str(base)) == str(tmp_path / "run_0000")
    (tmp_path / "run_0000").mkdir()
    assert next_versioned_path(str(base)) == str(tmp_path / "run_0001")


def test_next_versioned_path_does_not_claim(tmp_path):
    """next_versioned_path is pure — it never creates the returned dir."""
    base = tmp_path / "run"
    p = next_versioned_path(str(base))
    assert not Path(p).exists()


def test_policy_none_resolves_as_is(tmp_path):
    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out")})
    apply_save_dir_policy(cfg, None)
    assert cfg.save_dir == str(tmp_path / "out")


def test_policy_none_no_save_dir_is_noop():
    cfg = OmegaConf.create({"x": 1})
    apply_save_dir_policy(cfg, None)
    assert "save_dir" not in cfg


def test_policy_increment_claims_atomically(tmp_path):
    base = tmp_path / "exp" / "run"
    cfg = OmegaConf.create({"save_dir": str(base)})
    apply_save_dir_policy(cfg, "increment")
    assert Path(cfg.save_dir).name == "run_0000"
    # The claim is taken: the directory exists on disk.
    assert Path(cfg.save_dir).is_dir()


def test_policy_increment_advances_on_repeat(tmp_path):
    base = tmp_path / "run"
    for expected in ("run_0000", "run_0001", "run_0002"):
        cfg = OmegaConf.create({"save_dir": str(base)})
        apply_save_dir_policy(cfg, "increment")
        assert Path(cfg.save_dir).name == expected


def test_policy_increment_retries_on_collision(tmp_path, monkeypatch):
    """When next_versioned_path returns an already-claimed dir, retry."""
    base = tmp_path / "run"
    # Pre-claim run_0000 so the first mkdir(exist_ok=False) collides and the
    # loop must recompute (which then sees run_0000 exists → run_0001).
    (tmp_path / "run_0000").mkdir()

    calls = {"n": 0}
    import flexlock.save_dir as sd

    real = sd.next_versioned_path

    def flaky(path, fmt="_{i:04d}"):
        calls["n"] += 1
        if calls["n"] == 1:
            # Force a collision on the first attempt.
            return str(tmp_path / "run_0000")
        return real(path, fmt)

    monkeypatch.setattr(sd, "next_versioned_path", flaky)
    cfg = OmegaConf.create({"save_dir": str(base)})
    apply_save_dir_policy(cfg, "increment")
    assert Path(cfg.save_dir).name == "run_0001"
    assert calls["n"] >= 2


def test_policy_timestamp(tmp_path):
    from datetime import datetime
    from flexlock import config

    base = tmp_path / "out"
    cfg = OmegaConf.create({"save_dir": str(base)})
    apply_save_dir_policy(cfg, "timestamp")
    parent, name = Path(cfg.save_dir).parent, Path(cfg.save_dir).name
    assert parent == base
    # The suffix parses back with the configured timestamp format.
    datetime.strptime(name, config.TIMESTAMP_FORMAT)


def test_policy_unknown_raises(tmp_path):
    from flexlock.exceptions import FlexLockValidationError

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out")})
    with pytest.raises(FlexLockValidationError):
        apply_save_dir_policy(cfg, "bogus")


def _claim_worker(base, q):
    cfg = OmegaConf.create({"save_dir": base})
    apply_save_dir_policy(cfg, "increment")
    q.put(cfg.save_dir)


def test_concurrent_increment_gets_distinct_dirs(tmp_path):
    """Two racing submits with 'increment' on the same base get distinct dirs.

    This is the race the old ${vinc:} resolver could not fix, because the
    claim was not taken inside the resolver.
    """
    base = str(tmp_path / "run")
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    procs = [ctx.Process(target=_claim_worker, args=(base, q)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    results = {q.get(), q.get()}
    assert len(results) == 2, f"expected distinct dirs, got {results}"
    for r in results:
        assert Path(r).is_dir()
