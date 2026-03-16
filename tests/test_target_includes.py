"""Tests for collect_target_include_patterns and _walk_targets."""

import pytest
from omegaconf import OmegaConf

from flexlock.utils import collect_target_include_patterns, _walk_targets


def test_walk_targets_flat():
    """Test collecting targets from a flat config."""
    cfg = {"_target_": "mymod.train", "lr": 0.01}
    targets = set()
    _walk_targets(cfg, targets)
    assert targets == {"mymod.train"}


def test_walk_targets_nested():
    """Test collecting targets from nested config with sub-objects."""
    cfg = {
        "_target_": "mymod.train",
        "model": {
            "_target_": "mymod.models.Transformer",
            "layers": 12,
        },
        "optimizer": {
            "_target_": "torch.optim.Adam",
            "lr": 0.01,
        },
    }
    targets = set()
    _walk_targets(cfg, targets)
    assert targets == {"mymod.train", "mymod.models.Transformer", "torch.optim.Adam"}


def test_walk_targets_with_list():
    """Test collecting targets from configs containing lists."""
    cfg = {
        "_target_": "mymod.train",
        "callbacks": [
            {"_target_": "mymod.callbacks.EarlyStopping"},
            {"_target_": "mymod.callbacks.Checkpoint"},
        ],
    }
    targets = set()
    _walk_targets(cfg, targets)
    assert targets == {
        "mymod.train",
        "mymod.callbacks.EarlyStopping",
        "mymod.callbacks.Checkpoint",
    }


def test_walk_targets_skips_snapshot():
    """Test that _snapshot_ subtree is skipped."""
    cfg = {
        "_target_": "mymod.train",
        "_snapshot_": {
            "repos": {"main": {"_target_": "should.be.skipped"}},
        },
    }
    targets = set()
    _walk_targets(cfg, targets)
    assert targets == {"mymod.train"}


def test_walk_targets_omegaconf():
    """Test that DictConfig and ListConfig are handled."""
    cfg = OmegaConf.create({
        "_target_": "mymod.train",
        "model": {"_target_": "mymod.Model"},
        "items": [{"_target_": "mymod.Item"}],
    })
    targets = set()
    _walk_targets(cfg, targets)
    assert targets == {"mymod.train", "mymod.Model", "mymod.Item"}


def test_walk_targets_empty():
    """Test with config that has no targets."""
    cfg = {"lr": 0.01, "epochs": 10}
    targets = set()
    _walk_targets(cfg, targets)
    assert targets == set()


def test_collect_patterns_resolves_real_modules():
    """Test that real importable modules resolve to file paths."""
    # Use flexlock's own modules as test targets
    cfg = {"_target_": "flexlock.utils.instantiate"}
    import flexlock.utils
    import os
    import inspect

    repo_path = os.path.dirname(os.path.dirname(inspect.getfile(flexlock.utils)))
    patterns = collect_target_include_patterns(cfg, repo_path=repo_path)
    assert len(patterns) >= 1
    assert any("utils.py" in p for p in patterns)


def test_collect_patterns_skips_external():
    """Test that external modules (site-packages) are skipped."""
    cfg = {"_target_": "json.loads"}
    # json is a stdlib module, should be outside any repo
    patterns = collect_target_include_patterns(cfg, repo_path="/nonexistent/repo")
    assert patterns == []


def test_collect_patterns_skips_unresolvable():
    """Test that unresolvable targets are silently skipped."""
    cfg = {"_target_": "nonexistent_package.nonexistent_module.func"}
    patterns = collect_target_include_patterns(cfg, repo_path="/some/repo")
    assert patterns == []


def test_collect_patterns_deduplicates():
    """Test that duplicate targets produce unique patterns."""
    cfg = {
        "_target_": "flexlock.utils.instantiate",
        "sub": {"_target_": "flexlock.utils.to_dictconfig"},
    }
    import flexlock.utils
    import os
    import inspect

    repo_path = os.path.dirname(os.path.dirname(inspect.getfile(flexlock.utils)))
    patterns = collect_target_include_patterns(cfg, repo_path=repo_path)
    # Both targets resolve to the same file (utils.py), should appear once
    assert len(patterns) == 1


def test_collect_patterns_empty_config():
    """Test with config that has no targets."""
    cfg = {"lr": 0.01}
    patterns = collect_target_include_patterns(cfg)
    assert patterns == []
