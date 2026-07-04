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
