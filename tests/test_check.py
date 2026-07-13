"""Tests for Project.check — side-effect-free preflight resolution (Phase 4)."""

from pathlib import Path

from omegaconf import OmegaConf

from flexlock.api import Project


def _proj():
    return Project.__new__(Project)


def test_check_ok_returns_empty():
    cfg = OmegaConf.create({"a": "${b}", "b": "x"})
    assert _proj().check(cfg) == []


def test_check_reports_every_unresolved_leaf():
    cfg = OmegaConf.create({"a": "${missing}", "d": "prefix/${also_missing}"})
    errs = _proj().check(cfg)
    keys = sorted(e["full_key"] for e in errs)
    assert keys == ["a", "d"]
    assert all(e["item"] is None for e in errs)


def test_check_preserves_deferred_resolvers(tmp_path):
    """run_lock is stubbed during check, so a missing run.lock is NOT an error
    (it fires later, on the worker)."""
    cfg = OmegaConf.create(
        {"dir": str(tmp_path / "nope"), "x": "${run_lock:${dir},config.k}"}
    )
    assert _proj().check(cfg) == []


def test_check_is_side_effect_free(tmp_path):
    """vinc is stubbed during check — no directory is created."""
    base = tmp_path / "run"
    cfg = OmegaConf.create({"save_dir": "${vinc:" + str(base) + "}"})
    assert _proj().check(cfg) == []
    # next_versioned_path would have created the parent; check must not.
    assert not (tmp_path / "run_0000").exists()
    assert not base.parent.joinpath("run").exists()


def test_check_sweep_items_resolve_injected_key():
    cfg = OmegaConf.create({"save_dir": "out/${variable}", "bad": "${nope}"})
    errs = _proj().check(cfg, sweep=["hs", "phs0"], sweep_target="variable")
    # `variable` resolves per item; only `bad` fails, once per item.
    assert sorted((e["item"], e["full_key"]) for e in errs) == [
        (0, "bad"),
        (1, "bad"),
    ]


def test_check_does_not_mutate_defaults():
    defaults = OmegaConf.create({"save_dir": "out", "a": "${b}", "b": "x"})
    proj = _proj()
    proj.defaults = defaults
    proj.check(overrides={"b": "y"})
    # The override must not leak into the project defaults.
    assert defaults.b == "x"
