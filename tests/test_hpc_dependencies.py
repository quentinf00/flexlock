"""Scheduler dependencies and captureable IDs across submission paths."""

from unittest.mock import MagicMock

import pytest
from omegaconf import OmegaConf

from flexlock.api import ExecutionResult, Project
from flexlock.backends.dependencies import normalize_after
from flexlock.backends.pbs import PBSBackend
from flexlock.backends.slurm import SlurmBackend
from flexlock.exceptions import FlexLockValidationError
from flexlock.runner import FlexLockRunner


def target(save_dir, x=1):
    return {"x": x}


def cfg(root):
    return OmegaConf.create({
        "_target_": "tests.test_hpc_dependencies.target",
        "save_dir": str(root), "x": 1,
    })


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    profile = tmp_path / "slurm.yaml"
    profile.write_text("startup_lines: ['#SBATCH --partition=cpu', 'cd $SLURM_SUBMIT_DIR']\n")
    backend = MagicMock()
    backend.submit.return_value.job_id = "9001"
    constructor = MagicMock(return_value=backend)
    monkeypatch.setattr("flexlock.parallel.SlurmBackend", constructor)
    return str(profile), constructor, backend


def test_normalize_dependency_ids():
    assert normalize_after("42:43:42") == ["42", "43"]
    assert normalize_after([42, "43"]) == ["42", "43"]
    assert normalize_after(["42[].server"]) == ["42[].server"]


@pytest.mark.parametrize("value", ["", "42:bad", "42;echo", "-1", "42\ncommand"])
def test_reject_invalid_dependency_ids(value):
    with pytest.raises(FlexLockValidationError):
        normalize_after(value)


@pytest.mark.parametrize("backend,directive", [
    (SlurmBackend, "#SBATCH --dependency=afterok:42:43"),
    (PBSBackend, "#PBS -W depend=afterok:42:43"),
])
def test_dependency_directive_precedes_shell_commands(tmp_path, backend, directive):
    instance = backend(tmp_path, startup_lines=["cd /project"], after=[42, 43])
    lines = instance.render_script().splitlines()
    assert directive in lines
    assert lines.index(directive) < lines.index("cd /project")


def test_pbs_qualified_job_id(tmp_path):
    instance = PBSBackend(tmp_path, startup_lines=[], after="42.server:43.server")
    assert "#PBS -W depend=afterok:42.server:43.server" in instance.render_script()
    with pytest.raises(FlexLockValidationError, match="numeric"):
        SlurmBackend(tmp_path, startup_lines=[], after="42.server")


@pytest.mark.parametrize("backend,line", [
    (SlurmBackend, "#SBATCH --dependency=afterok:41"),
    (PBSBackend, "#PBS -W depend=afterok:41"),
])
def test_conflicting_dependency_configuration(tmp_path, backend, line):
    with pytest.raises(FlexLockValidationError, match="not both"):
        backend(tmp_path, startup_lines=[line], after=[42])


def test_after_requires_scheduler_before_creating_output(tmp_path):
    root = tmp_path / "output"
    with pytest.raises(FlexLockValidationError, match="backend"):
        Project().submit(cfg(root), after=[42])
    with pytest.raises(FlexLockValidationError, match="backend"):
        Project().submit_pipeline([[cfg(root)]], after=[42])
    assert not root.exists()


def test_single_submission_returns_id_without_waiting(tmp_path, scheduler):
    profile, constructor, backend = scheduler
    result = Project().submit(cfg(tmp_path / "out"), slurm_config=profile,
                              after=[42, 43], wait=False, smart_run=False)
    assert result.status == "SUBMITTED" and result.job_id == "9001"
    assert constructor.call_args.kwargs["after"] == ["42", "43"]
    backend.is_terminal.assert_not_called()


@pytest.mark.parametrize("pipeline", [False, True])
def test_collection_results_keep_submitted_id(tmp_path, scheduler, pipeline):
    profile, constructor, _ = scheduler
    kwargs = dict(slurm_config=profile, after=[42], wait=False, smart_run=False)
    if pipeline:
        results = Project().submit_pipeline([
            [cfg(tmp_path / "out" / "i0" / "a"), cfg(tmp_path / "out" / "i0" / "b")],
            [cfg(tmp_path / "out" / "i1" / "a"), cfg(tmp_path / "out" / "i1" / "b")],
        ], **kwargs)
        results = [stage for item in results for stage in item]
    else:
        results = Project().submit(cfg(tmp_path / "out" / "base"), sweep=[
            {"x": 2, "save_dir": str(tmp_path / "out" / "a")},
            {"x": 3, "save_dir": str(tmp_path / "out" / "b")},
        ], **kwargs)
    assert all(result.job_id == "9001" for result in results)
    assert all(result.status == "SUBMITTED" for result in results)
    assert constructor.call_args.kwargs["after"] == ["42"]


def test_cli_prints_only_id(tmp_path, scheduler, capsys):
    profile, constructor, _ = scheduler
    config = tmp_path / "config.yaml"
    config.write_text(OmegaConf.to_yaml(cfg(tmp_path / "out")))
    FlexLockRunner().run(["-c", str(config), "--slurm-config", profile,
                          "--after", "42:43", "--print-job-id"])
    assert capsys.readouterr().out == "9001\n"
    assert constructor.call_args.kwargs["after"] == ["42", "43"]


@pytest.mark.parametrize("pipeline", [False, True])
def test_cli_collection_prints_id_once(tmp_path, scheduler, capsys, pipeline):
    profile, _, _ = scheduler
    config = tmp_path / "config.yaml"
    root = tmp_path / "out"
    if pipeline:
        config.write_text(OmegaConf.to_yaml({"a": cfg(root / "a"), "b": cfg(root / "b")}))
        selection = ["-s", "a", "b"]
    else:
        config.write_text(OmegaConf.to_yaml(cfg(root)))
        selection = ["--sweep", "x=2,x=3"]
    FlexLockRunner().run(["-c", str(config), *selection, "--slurm-config", profile,
                          "--after", "42", "--print-job-id"])
    assert capsys.readouterr().out == "9001\n"


def test_cli_rejects_preview_and_local_id_output(tmp_path, scheduler):
    profile, _, _ = scheduler
    with pytest.raises(FlexLockValidationError, match="backend"):
        FlexLockRunner().run(["--print-job-id"])
    with pytest.raises(FlexLockValidationError, match="preview"):
        FlexLockRunner().run(["--slurm-config", profile, "--dry-run", "--print-job-id"])
    queue = tmp_path / "queue.yaml"
    with pytest.raises(FlexLockValidationError, match="dequeuing"):
        FlexLockRunner().run(["--slurm-config", profile, "--after", "42",
                              "--enqueue", str(queue)])
    assert not queue.exists()


def test_dry_run_renders_dependency_without_output_dir(tmp_path, scheduler, capsys):
    profile, _, _ = scheduler
    root = tmp_path / "output"
    Project().submit(cfg(root), slurm_config=profile, after=[42], dry_run=True)
    assert "#SBATCH --dependency=afterok:42" in capsys.readouterr().out
    assert not root.exists()


def test_result_payload_cannot_shadow_job_id():
    result = ExecutionResult("output", "SUCCESS", result={"job_id": "user"}, job_id="42")
    assert result.job_id == "42" and result["job_id"] == "user"
