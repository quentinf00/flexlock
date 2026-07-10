"""Tests for the shipped skills + `flexlock skills` (Phase C)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from flexlock.cli import _iter_skills, _parse_skill_frontmatter, main

EXPECTED = {
    "flexlock-survey",
    "flexlock-new-stage",
    "flexlock-run-and-watch",
    "flexlock-report",
}


def test_four_skills_packaged():
    names = {name for name, _, _ in _iter_skills()}
    assert EXPECTED <= names


def test_frontmatter_parses_for_all():
    for name, desc, entry in _iter_skills():
        meta = _parse_skill_frontmatter(entry.joinpath("SKILL.md").read_text())
        assert meta.get("name")
        assert meta.get("description")
        assert desc == meta["description"]


def test_skills_list(capsys):
    with patch("sys.argv", ["flexlock", "skills", "list"]):
        main()
    out = capsys.readouterr().out
    for name in EXPECTED:
        assert name in out


def test_skills_install_copies_folders(tmp_path, capsys):
    dest = tmp_path / "skills"
    with patch("sys.argv", ["flexlock", "skills", "install", "--dest", str(dest)]):
        main()
    for name in EXPECTED:
        assert (dest / name / "SKILL.md").is_file()


def test_skills_install_refuses_overwrite_without_force(tmp_path, capsys):
    dest = tmp_path / "skills"
    with patch("sys.argv", ["flexlock", "skills", "install", "flexlock-survey",
                            "--dest", str(dest)]):
        main()
    # Second install without --force skips.
    with patch("sys.argv", ["flexlock", "skills", "install", "flexlock-survey",
                            "--dest", str(dest)]):
        main()
    out = capsys.readouterr().out
    assert "Skipping flexlock-survey" in out

    # With --force it overwrites.
    with patch("sys.argv", ["flexlock", "skills", "install", "flexlock-survey",
                            "--dest", str(dest), "--force"]):
        main()
    out = capsys.readouterr().out
    assert "Installed" in out


def test_skills_install_unknown_name(tmp_path):
    dest = tmp_path / "skills"
    with patch("sys.argv", ["flexlock", "skills", "install", "nope", "--dest", str(dest)]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
