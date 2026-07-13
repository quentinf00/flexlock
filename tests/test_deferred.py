"""Tests for the deferred-resolution mechanism (Phase 2a / 2c).

``deferred_stubbed`` and ``resolve_deferred`` replace the hand-rolled freeze
grammar with OmegaConf's own resolution, exploiting the fact that OmegaConf
pre-resolves a resolver's arguments before invoking it.
"""

import yaml
from omegaconf import OmegaConf

from flexlock.resolvers import deferred_stubbed, resolve_deferred


def test_omegaconf_preresolves_resolver_args():
    """Pinned-behaviour gate (Risk #1 in the plan).

    OmegaConf must resolve nested interpolations in a resolver's args *before*
    calling the resolver. If a future omegaconf changes this, deferred_stubbed
    breaks — this test fails loudly first.
    """
    seen = []

    def probe(*args):
        seen.append(tuple(args))
        return "x"

    OmegaConf.register_new_resolver("probe", probe, replace=True, use_cache=False)
    try:
        cfg = OmegaConf.create(
            {"dir": "/data/precomputed", "v": "${probe:${dir},config.key}"}
        )
        OmegaConf.resolve(cfg)
    finally:
        # Leave a harmless stub so global resolver state isn't left dangling.
        OmegaConf.register_new_resolver("probe", lambda *a: "", replace=True)
    assert seen == [("/data/precomputed", "config.key")]


def _raw(cfg, key):
    # The frozen call string is itself a live interpolation; read it as raw
    # text (resolve=False) so we don't trigger a real resolver call.
    return OmegaConf.to_container(cfg, resolve=False)[key]


def test_deferred_stubbed_freezes_run_lock_args():
    cfg = OmegaConf.create(
        {
            "precompute_dir": "/data/precomputed",
            "x": "${run_lock:${precompute_dir},config.zarr_path}",
        }
    )
    with deferred_stubbed():
        OmegaConf.resolve(cfg)
    assert _raw(cfg, "x") == "${run_lock:/data/precomputed,config.zarr_path}"


def test_deferred_stubbed_freezes_latest():
    cfg = OmegaConf.create({"x": "${latest:outputs/run_*}"})
    with deferred_stubbed():
        OmegaConf.resolve(cfg)
    assert _raw(cfg, "x") == "${latest:outputs/run_*}"


def test_deferred_stubbed_null_default_survives():
    cfg = OmegaConf.create(
        {"d": "/some/dir", "x": "${run_lock:${d},config.opt,null}"}
    )
    with deferred_stubbed():
        OmegaConf.resolve(cfg)
    assert _raw(cfg, "x") == "${run_lock:/some/dir,config.opt,null}"


def test_deferred_stubbed_restores_real_resolvers(tmp_path):
    """After the context exits, run_lock reads the real run.lock again."""
    run_dir = tmp_path / "up_0001"
    run_dir.mkdir()
    (run_dir / "run.lock").write_text(yaml.dump({"config": {"lr": 0.01}}))

    with deferred_stubbed():
        pass
    cfg = OmegaConf.create({"d": str(run_dir), "v": "${run_lock:${d},config.lr}"})
    assert OmegaConf.to_container(cfg, resolve=True)["v"] == 0.01


def test_resolve_deferred_fires_real_resolver(tmp_path):
    run_dir = tmp_path / "up_0001"
    run_dir.mkdir()
    (run_dir / "run.lock").write_text(
        yaml.dump({"config": {"stats": "/data/stats.json"}})
    )
    # Frozen call string as produced by deferred_stubbed at submit time.
    cfg = OmegaConf.create(
        {"stats": f"${{run_lock:{run_dir},config.stats}}"}
    )
    out = resolve_deferred(cfg)
    assert out.stats == "/data/stats.json"
    # Detached plain config: no live interpolation left.
    assert OmegaConf.to_container(out, resolve=False)["stats"] == "/data/stats.json"
