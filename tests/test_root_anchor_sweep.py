"""CLI root-anchor sweeps must bind each upstream before stage selection."""
import json
from pathlib import Path

import pytest
import yaml

from flexlock.record import load_record
from flexlock.runner import FlexLockRunner


def consume(input, save_dir, scale=1):
    result = {"input": input, "scale": scale}
    Path(save_dir, "product.json").write_text(json.dumps(result))
    return result


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEXLOCK_INDEX", str(tmp_path / ".flexlock/index.db"))
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[1]))
    for name in ["A", "B"]:
        upstream = tmp_path / name
        upstream.mkdir()
        (upstream / "run.lock").write_text(yaml.safe_dump({
            "config": {"output_path": f"/data/{name}.csv"},
        }))
    config = tmp_path / "cfgmod.py"
    config.write_text(
        "from flexlock import py2cfg\n"
        "from tests.test_root_anchor_sweep import consume\n"
        f"cfg = dict(upstream_run={str(tmp_path / 'A')!r}, label='A',\n"
        "    main=py2cfg(consume,\n"
        "        input='${run_lock:${upstream_run},config.output_path}',\n"
        f"        save_dir={str(tmp_path / 'outputs')!r} + '/${{label}}', scale=1,\n"
        "        _snapshot_=dict(prevs=['${upstream_run}'], repos={})))\n"
    )
    return tmp_path, ["-d", str(config) + ":cfg", "-s", "main"]


def items(root):
    return [{"upstream_run": str(root / name), "label": name, "scale": i}
            for i, name in enumerate(["A", "B"], 1)]


@pytest.mark.parametrize("n_jobs", [1, 2])
def test_python_root_anchor_sweep_executes_each_bound_input(project, n_jobs):
    root, command = project
    sweep = root / "items.yaml"
    sweep.write_text(yaml.safe_dump(items(root)))
    result = FlexLockRunner().run(command + [
        "--sweep-file", str(sweep), "--n_jobs", str(n_jobs),
    ])
    assert result == [{"input": "/data/A.csv", "scale": 1},
                      {"input": "/data/B.csv", "scale": 2}]
    for i, name in enumerate(["A", "B"], 1):
        record = load_record(root / "outputs" / name)
        assert record["config"]["input"] == f"/data/{name}.csv"
        assert record["config"]["scale"] == i
        assert "upstream_run" not in record["config"]
        assert any(link["path"] == str(root / name)
                   for link in record["lineage"].values())


def test_root_anchor_override_remains_supported(project):
    root, command = project
    result = FlexLockRunner().run(command + ["-o", f"upstream_run={root}/B"])
    assert result["input"] == "/data/B.csv"


def test_root_sweep_preview_and_enqueue_agree(project, capsys):
    root, command = project
    sweep = root / "items.yaml"
    sweep.write_text(yaml.safe_dump(items(root)))
    FlexLockRunner().run(command + ["--sweep-file", str(sweep), "--print-config"])
    preview = capsys.readouterr().out
    assert f"run_lock:{root}/A,config.output_path" in preview
    assert f"run_lock:{root}/B,config.output_path" in preview
    assert not (root / "outputs").exists()
    queue = root / "queue.yaml"
    FlexLockRunner().run(command + ["--sweep-file", str(sweep), "--enqueue", str(queue)])
    queued = yaml.safe_load(queue.read_text())
    assert [cfg["scale"] for cfg in queued] == [1, 2]
    assert [cfg["input"] for cfg in queued] == [
        f"${{run_lock:{root}/{name},config.output_path}}" for name in ["A", "B"]]
    assert all("upstream_run" not in cfg for cfg in queued)
    result = FlexLockRunner().run(["--sweep-file", str(queue)])
    assert [item["input"] for item in result] == ["/data/A.csv", "/data/B.csv"]


@pytest.mark.parametrize("scalar", [False, True])
def test_cli_string_and_scalar_root_sweeps(project, scalar):
    root, command = project
    # Use a stage-local output naming override for the two products.
    command += ["-O", f"save_dir={root}/outputs/${{input}}"]
    if scalar:
        command += ["--sweep", f"{root}/A,{root}/B", "--sweep-target", "upstream_run"]
    else:
        command += ["--sweep", f"upstream_run={root}/A,upstream_run={root}/B"]
    result = FlexLockRunner().run(command)
    assert [item["input"] for item in result] == ["/data/A.csv", "/data/B.csv"]


def test_root_sweep_key_check_and_dump(project, capsys):
    root, command = project
    config = Path(command[1].removesuffix(":cfg"))
    with config.open("a") as stream:
        stream.write(f"cfg['grid'] = {items(root)!r}\n")
    FlexLockRunner().run(command + ["--sweep-key", "grid", "--check"])
    assert "check OK" in capsys.readouterr().out
    FlexLockRunner().run(command + ["--sweep-key", "grid", "--dump"])
    dumped = yaml.safe_load(capsys.readouterr().out)
    assert [cfg["input"] for cfg in dumped] == [
        f"${{run_lock:{root}/{name},config.output_path}}" for name in ["A", "B"]]
    assert not (root / "outputs").exists()


def test_root_sweep_applies_selected_merge_and_override(project):
    root, command = project
    sweep = root / "items.yaml"
    sweep.write_text(yaml.safe_dump(items(root)))
    merge = root / "merge.yaml"
    merge.write_text("scale: 3\n")
    result = FlexLockRunner().run(command + [
        "--sweep-file", str(sweep), "-M", str(merge), "-O", "scale=4",
    ])
    assert result == [{"input": "/data/A.csv", "scale": 4},
                      {"input": "/data/B.csv", "scale": 4}]


def test_stage_only_and_qualified_stage_sweeps_keep_scope(project):
    root, command = project
    # A same-name root value must not steal an existing bare stage argument.
    config = Path(command[1].removesuffix(":cfg"))
    with config.open("a") as stream:
        stream.write("cfg['scale'] = 99\n")
    for qualified in [False, True]:
        key = "main.scale" if qualified else "scale"
        branch = "qualified" if qualified else "bare"
        result = FlexLockRunner().run(command + [
            "--sweep", f"{key}=2,{key}=3", "-O",
            f"save_dir={root}/{branch}/${{scale}}",
        ])
        assert [item["scale"] for item in result] == [2, 3]


def test_root_sweep_scheduler_receives_compiled_items(project, monkeypatch):
    from unittest.mock import MagicMock
    from flexlock.taskdb import get_all_tasks

    root, command = project
    profile = root / "slurm.yaml"
    profile.write_text("startup_lines: []\n")
    backend = MagicMock()
    backend.submit.return_value.job_id = "42"
    constructor = MagicMock(return_value=backend)
    monkeypatch.setattr("flexlock.parallel.SlurmBackend", constructor)
    sweep = root / "items.yaml"
    sweep.write_text(yaml.safe_dump(items(root)))
    FlexLockRunner().run(command + [
        "--sweep-file", str(sweep), "--slurm-config", str(profile), "--print-job-id",
    ])
    backend.submit.assert_called_once()
    queued = get_all_tasks(root / "outputs/run.lock.tasks.db")
    assert sorted(row["task"]["input"] for row in queued) == ["/data/A.csv", "/data/B.csv"]
    assert all("upstream_run" not in row["task"] for row in queued)


def test_mixed_scalar_root_sweep_has_actionable_error(project):
    from flexlock.exceptions import FlexLockValidationError

    root, command = project
    with pytest.raises(FlexLockValidationError, match="repeat the key"):
        FlexLockRunner().run(command + ["--sweep", f"upstream_run={root}/A,{root}/B"])
    assert not (root / "outputs").exists()
