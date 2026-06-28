"""Tests for Slurm script validation + dry_run preview (Spec G)."""

from pathlib import Path

import pytest
import yaml
from omegaconf import OmegaConf

from flexlock.backends.slurm import SlurmBackend, validate_slurm_script


# Each warning has a unique substring we can match without pinning the
# whole message.
W_PARTITION = "--partition"
W_CD = "'cd'"
W_ENV = "activation"
W_GPU = "--gres"


def _script(*lines: str) -> str:
    return "\n".join(("#!/bin/bash", *lines))


# --- validate_slurm_script ---

def test_validate_clean_config_no_warnings():
    s = _script(
        "#SBATCH --partition=gpu",
        "#SBATCH --gres=gpu:1",
        "#SBATCH --time=24:00:00",
        "cd $SLURM_SUBMIT_DIR",
        'eval "$(pixi shell-hook)"',
        "python - <<'PY'",
        "print('ok')",
        "PY",
    )
    assert validate_slurm_script(s, expects_gpu=True) == []


def test_validate_missing_partition():
    s = _script(
        "#SBATCH --time=01:00:00",
        "cd $SLURM_SUBMIT_DIR",
        'eval "$(pixi shell-hook)"',
    )
    warnings = validate_slurm_script(s)
    assert any(W_PARTITION in w for w in warnings)


def test_validate_short_partition_flag_p_accepted():
    """-p partition_name should not trigger the missing-partition warning."""
    s = _script(
        "#SBATCH -p gpu",
        "cd $SLURM_SUBMIT_DIR",
        'eval "$(pixi shell-hook)"',
    )
    warnings = validate_slurm_script(s)
    assert not any(W_PARTITION in w for w in warnings)


def test_validate_missing_cd():
    s = _script(
        "#SBATCH --partition=gpu",
        'eval "$(pixi shell-hook)"',
    )
    warnings = validate_slurm_script(s)
    assert any(W_CD in w for w in warnings)


def test_validate_missing_env_activation():
    s = _script(
        "#SBATCH --partition=gpu",
        "cd $SLURM_SUBMIT_DIR",
        "python script.py",
    )
    warnings = validate_slurm_script(s)
    assert any(W_ENV in w for w in warnings)


def test_validate_recognises_conda_activate():
    s = _script(
        "#SBATCH --partition=gpu",
        "cd $SLURM_SUBMIT_DIR",
        "conda activate myenv",
    )
    warnings = validate_slurm_script(s)
    assert not any(W_ENV in w for w in warnings)


def test_validate_recognises_module_load():
    s = _script(
        "#SBATCH --partition=gpu",
        "cd $SLURM_SUBMIT_DIR",
        "module load python/3.11",
    )
    warnings = validate_slurm_script(s)
    assert not any(W_ENV in w for w in warnings)


def test_validate_recognises_source_activate():
    s = _script(
        "#SBATCH --partition=gpu",
        "cd $SLURM_SUBMIT_DIR",
        "source venv/bin/activate",
    )
    warnings = validate_slurm_script(s)
    assert not any(W_ENV in w for w in warnings)


def test_validate_gpu_expected_but_missing():
    s = _script(
        "#SBATCH --partition=gpu",
        "cd $SLURM_SUBMIT_DIR",
        'eval "$(pixi shell-hook)"',
    )
    warnings = validate_slurm_script(s, expects_gpu=True)
    assert any(W_GPU in w for w in warnings)


def test_validate_gpu_present_no_warning():
    s = _script(
        "#SBATCH --partition=gpu",
        "#SBATCH --gres=gpu:1",
        "cd $SLURM_SUBMIT_DIR",
        'eval "$(pixi shell-hook)"',
    )
    warnings = validate_slurm_script(s, expects_gpu=True)
    assert not any(W_GPU in w for w in warnings)


# --- SlurmBackend.render_script ---

def test_render_script_includes_startup_lines(tmp_path):
    backend = SlurmBackend(
        folder=tmp_path,
        startup_lines=[
            "#SBATCH --partition=gpu",
            "cd $SLURM_SUBMIT_DIR",
            'eval "$(pixi shell-hook)"',
        ],
        python_exe="python",
    )
    script = backend.render_script()
    assert "#SBATCH --partition=gpu" in script
    assert "cd $SLURM_SUBMIT_DIR" in script


def test_render_script_validation_clean(tmp_path):
    backend = SlurmBackend(
        folder=tmp_path,
        startup_lines=[
            "#SBATCH --partition=gpu",
            "#SBATCH --gres=gpu:1",
            "cd $SLURM_SUBMIT_DIR",
            'eval "$(pixi shell-hook)"',
        ],
        python_exe="python",
    )
    assert validate_slurm_script(backend.render_script(), expects_gpu=True) == []


def test_render_script_validation_catches_missing_partition(tmp_path):
    backend = SlurmBackend(
        folder=tmp_path,
        startup_lines=[
            "cd $SLURM_SUBMIT_DIR",
            'eval "$(pixi shell-hook)"',
        ],
        python_exe="python",
    )
    warnings = validate_slurm_script(backend.render_script())
    assert any(W_PARTITION in w for w in warnings)


# --- is_terminal (orphan reconciliation depends on this) ---

@pytest.mark.parametrize("status,expected", [
    ("PENDING", False),
    ("RUNNING", False),
    ("CONFIGURING", False),
    ("unknown", False),          # racy/unreported: must NOT look terminal
    ("", False),
    ("COMPLETED", True),
    ("FAILED", True),
    ("TIMEOUT", True),
    ("OUT_OF_MEMORY", True),
    ("CANCELLED by 12345", True),  # sacct verbose form
    ("CANCELLED+", True),          # truncated form
])
def test_slurm_is_terminal(tmp_path, monkeypatch, status, expected):
    backend = SlurmBackend(folder=tmp_path, startup_lines=[], python_exe="python")
    monkeypatch.setattr(backend, "check_status", lambda job_id: status)
    assert backend.is_terminal("123") is expected


# --- dry_run end-to-end ---

def _write_slurm_yaml(path: Path, *, partition="gpu", with_cd=True, with_env=True):
    lines = [f"#SBATCH --partition={partition}", "#SBATCH --gres=gpu:1"]
    if with_cd:
        lines.append("cd $SLURM_SUBMIT_DIR")
    if with_env:
        lines.append('eval "$(pixi shell-hook)"')
    path.write_text(yaml.safe_dump({
        "startup_lines": lines,
        "python_exe": "python",
    }))


def test_dry_run_prints_script_and_skips_submit(tmp_path, capsys):
    from flexlock import Project

    slurm_yaml = tmp_path / "slurm_gpu.yaml"
    _write_slurm_yaml(slurm_yaml)

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "x": 1})
    result = Project().submit(
        cfg, slurm_config=str(slurm_yaml), dry_run=True
    )

    assert result is None
    out = capsys.readouterr().out
    assert "Slurm submission script (dry run)" in out
    assert "#SBATCH --partition=gpu" in out
    assert "cd $SLURM_SUBMIT_DIR" in out


def test_dry_run_surfaces_warnings(tmp_path, capsys):
    from flexlock import Project

    slurm_yaml = tmp_path / "slurm.yaml"
    _write_slurm_yaml(slurm_yaml, with_cd=False, with_env=False)

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "x": 1})
    Project().submit(cfg, slurm_config=str(slurm_yaml), dry_run=True)
    out = capsys.readouterr().out
    assert "Warnings:" in out
    assert "'cd'" in out
    assert "activation" in out


def test_dry_run_local_is_noop(tmp_path, capsys):
    from flexlock import Project

    cfg = OmegaConf.create({"save_dir": str(tmp_path / "out"), "x": 1})
    result = Project().submit(cfg, dry_run=True)  # no slurm_config
    assert result is None
    out = capsys.readouterr().out
    # No script printed; the "no-op" message is logged, not printed
    assert "Slurm submission script" not in out
