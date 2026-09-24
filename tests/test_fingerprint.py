"""Tests for the pure run fingerprint digest (Phase 2.1)."""

import pytest
from git import Repo
from pathlib import Path
from omegaconf import OmegaConf

from flexlock.fingerprint import fingerprint, canonical_config, SAVE_DIR_PLACEHOLDER


@pytest.fixture
def git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = Repo.init(repo_dir)
    (repo_dir / "model.py").write_text("VERSION = 1\n")
    (repo_dir / "notes.md").write_text("hello\n")
    repo.index.add(["model.py", "notes.md"])
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.commit("init")
    return repo_dir


# ── config canonicalization ──


def test_same_config_same_digest():
    cfg = OmegaConf.create({"lr": 0.1, "epochs": 3, "save_dir": "outputs/a"})
    assert fingerprint(cfg) == fingerprint(OmegaConf.create(dict(cfg)))


def test_save_dir_change_alone_does_not_change_digest():
    a = OmegaConf.create({"lr": 0.1, "save_dir": "outputs/run_a"})
    b = OmegaConf.create({"lr": 0.1, "save_dir": "outputs/run_b"})
    assert fingerprint(a) == fingerprint(b)


def test_nested_save_dir_prefix_normalized():
    cfg = OmegaConf.create(
        {
            "save_dir": "outputs/run_a",
            "logger": "outputs/run_a/logs",
            "unrelated": "outputs/run_a_sibling",  # not a path prefix
        }
    )
    canon = canonical_config(cfg)
    assert canon["logger"] == SAVE_DIR_PLACEHOLDER + "/logs"
    # A sibling that merely shares the string prefix must NOT be normalized.
    assert canon["unrelated"] == "outputs/run_a_sibling"


def test_config_value_change_changes_digest():
    a = OmegaConf.create({"lr": 0.1, "save_dir": "outputs/a"})
    b = OmegaConf.create({"lr": 0.2, "save_dir": "outputs/a"})
    assert fingerprint(a) != fingerprint(b)


def test_snapshot_key_ignored():
    a = OmegaConf.create({"lr": 0.1, "save_dir": "outputs/a"})
    b = OmegaConf.create(
        {"lr": 0.1, "save_dir": "outputs/a", "_snapshot_": {"repos": {"m": "."}}}
    )
    assert fingerprint(a) == fingerprint(b)


# ── repo tree hashing with include/exclude ──


def test_include_relevant_change_changes_digest(git_repo):
    repos = {"main": {"path": str(git_repo), "include": ["model.py"]}}
    cfg = OmegaConf.create({"save_dir": "outputs/a"})
    before = fingerprint(cfg, repos=repos)

    (git_repo / "model.py").write_text("VERSION = 2\n")
    after = fingerprint(cfg, repos=repos)
    assert before != after


def test_excluded_change_does_not_change_digest(git_repo):
    repos = {"main": {"path": str(git_repo), "exclude": ["*.md"]}}
    cfg = OmegaConf.create({"save_dir": "outputs/a"})
    before = fingerprint(cfg, repos=repos)

    (git_repo / "notes.md").write_text("changed docs\n")
    after = fingerprint(cfg, repos=repos)
    assert before == after


def test_change_outside_include_does_not_change_digest(git_repo):
    repos = {"main": {"path": str(git_repo), "include": ["model.py"]}}
    cfg = OmegaConf.create({"save_dir": "outputs/a"})
    before = fingerprint(cfg, repos=repos)

    (git_repo / "notes.md").write_text("irrelevant\n")
    after = fingerprint(cfg, repos=repos)
    assert before == after


# ── data hashing ──


def test_data_change_changes_digest(tmp_path):
    data_file = tmp_path / "data.csv"
    data_file.write_text("1,2,3\n")
    cfg = OmegaConf.create({"save_dir": "outputs/a"})
    data = {"train": str(data_file)}

    before = fingerprint(cfg, data=data, use_cache=False)
    data_file.write_text("4,5,6\n")
    after = fingerprint(cfg, data=data, use_cache=False)
    assert before != after


# ── environment lockfiles ──


def _repos(git_repo):
    # Narrowed to model.py, as for auto-detected _target_ modules: the
    # lockfile is outside the tree hash, so only the env part can see it.
    return {"main": {"path": str(git_repo), "include": ["model.py"]}}


def test_lockfile_change_changes_digest(git_repo):
    cfg = OmegaConf.create({"lr": 0.1, "save_dir": "outputs/a"})
    lock = git_repo / "pixi.lock"
    lock.write_text("numpy==2.0\n")
    before = fingerprint(cfg, repos=_repos(git_repo), data=None)
    lock.write_text("numpy==2.1\n")
    after = fingerprint(cfg, repos=_repos(git_repo), data=None)
    assert before != after


def test_lockfile_found_from_repo_subdir(git_repo):
    from flexlock.fingerprint import env_hashes

    (git_repo / "uv.lock").write_text("x\n")
    sub = git_repo / "pkg"
    sub.mkdir()
    assert list(env_hashes({"main": {"path": str(sub)}})) == ["main/uv.lock"]


def test_no_lockfile_leaves_digest_unchanged(git_repo, monkeypatch):
    cfg = OmegaConf.create({"lr": 0.1, "save_dir": "outputs/a"})
    with_env = fingerprint(cfg, repos=_repos(git_repo), data=None)
    monkeypatch.setenv("FLEXLOCK_HASH_ENV", "0")
    assert fingerprint(cfg, repos=_repos(git_repo), data=None) == with_env


def test_hash_env_opt_out(git_repo, monkeypatch):
    cfg = OmegaConf.create({"lr": 0.1, "save_dir": "outputs/a"})
    (git_repo / "pixi.lock").write_text("a\n")
    on = fingerprint(cfg, repos=_repos(git_repo), data=None)
    monkeypatch.setenv("FLEXLOCK_HASH_ENV", "0")
    off = fingerprint(cfg, repos=_repos(git_repo), data=None)
    (git_repo / "pixi.lock").write_text("b\n")
    assert on != off
    assert fingerprint(cfg, repos=_repos(git_repo), data=None) == off


def test_lockfile_names_override(git_repo, monkeypatch):
    from flexlock.fingerprint import env_hashes

    (git_repo / "pixi.lock").write_text("a\n")
    (git_repo / "requirements.lock").write_text("b\n")
    monkeypatch.setenv("FLEXLOCK_ENV_LOCKFILES", "requirements.lock")
    assert list(env_hashes(_repos(git_repo))) == ["main/requirements.lock"]


def test_rundiff_env_legacy_target_matches():
    from flexlock.diff import RunDiff

    cur = {"config": {}, "env": {"main/pixi.lock": "a"}}
    assert RunDiff(cur, {"config": {}}).compare_env()
    d = RunDiff(cur, {"config": {}, "env": {"main/pixi.lock": "b"}})
    assert not d.is_match()
    assert d.diffs["env"] == ["main/pixi.lock: lockfile changed"]
