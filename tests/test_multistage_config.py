"""
Tests for FlexLock configuration handling, focusing on:
1. Interpolation context preservation (Outer -> Inner).
2. Selection logic.
3. Sweep execution with interpolated values.
"""

import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from omegaconf import OmegaConf
from flexlock import flexcli
from loguru import logger
logger.enable("flexlock")
# --- Helpers ---

@pytest.fixture
def temp_yaml():
    """Creates a temporary YAML file and cleans it up."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    path = Path(f.name)
    yield f, path
    f.close()
    if path.exists():
        path.unlink()


@pytest.fixture(autouse=True)
def _clean_shared_save_dir():
    """These tests reuse hardcoded /tmp/flexlock_test save_dirs; wipe them so
    the collision guard doesn't trip on a previous session's run.lock."""
    import shutil

    shutil.rmtree("/tmp/flexlock_test", ignore_errors=True)
    yield

def mock_argv(args):
    """Context manager to patch sys.argv."""
    return patch.object(sys, "argv", ["script.py"] + args)

# --- Tests ---

# Define the application logic
@flexcli
def main(p, save_dir=None):
    return p

def test_interpolation_with_selection(temp_yaml):
    """
    Test that selecting a sub-node (Inner Config) retains access to 
    variables defined in the Root (Outer Config) via interpolation.
    """
    f, config_path = temp_yaml
    
    # Define a config where the experiment depends on a global parameter
    f.write("""
global_param: 42

experiments:
  exp_a:
    # This interpolation requires access to the root node
    p: ${global_param}
    save_dir: "/tmp/flexlock_test/exp_a"
""")
    f.close()


    # Run with selection
    with mock_argv(["-c", str(config_path), "-s", "experiments.exp_a"]):
        result = main()
    
    assert result == 42, "Failed to resolve root interpolation after selection."

# Capture results to verify sweep execution
results = []

@flexcli
def main3(p, save_dir):
    logger.info(f"Running with p={p}, save_dir={save_dir}")
    results.append(p)
    return p

def test_interpolation_in_sweep_list(temp_yaml):
    """
    Test that items in a sweep list (defined in root) can interpolate 
    values from the root config when injected into the selected node.
    """
    f, config_path = temp_yaml
    
    # 1. global_mult is 10
    # 2. base_exp has p=1
    # 3. grid has two tasks: 
    #    - p=5
    #    - p=${global_mult} (Should resolve to 10)
    f.write("""
global_mult: 10

base_exp:
  p: 1
  save_dir: "${vinc:/tmp/flexlock_test}"

grid:
  - p: 5
  - p: ${global_mult}
""")
    f.close()


    # Run sweep
    with mock_argv([
        "-c", str(config_path),
        "-s", "base_exp",
        "--sweep-key", "grid",
        "--n_jobs", "1" 
    ]):
        main3()

    # Expecting [5, 10]
    assert 5 in results
    assert 10 in results, "Interpolation inside sweep list failed to resolve to global var."
    assert len(results) == 2

@flexcli
def main2(param, other, save_dir):
    return param, other

def test_inner_vs_outer_overrides(temp_yaml):
    """
    Test the distinction between:
    - Outer Overrides (-o): Affect global config (before selection).
    - Inner Overrides (-O): Affect selected config (after selection).
    """
    f, config_path = temp_yaml
    f.write("""
global_val: 10
nested:
  param: ${global_val}
  other: 0
""")
    f.close()


    # Case 1: Override Global Value (Outer)
    # Changing global_val to 99 should update nested.param via interpolation
    with mock_argv([
        "-c", str(config_path),
        "-s", "nested",
        "-o", "global_val=99" # Outer override
    ]):
        p, _ = main2()
        assert p == 99, "Outer override failed to update interpolated value."

    # Case 2: Override Selected Value (Inner)
    # We select 'nested', then override 'other'.
    # (global_val stays 10 from file)
    # No save_dir in the config → both cases fall back to the same
    # outputs/<name>/<timestamp> dir within one second; bypass the guard.
    with mock_argv([
        "-c", str(config_path),
        "-s", "nested",
        "-O", "other=5", # Inner override
        "--save-dir-policy", "unsafe",
    ]):
        p, o = main2()
        assert p == 10  # Original file value
        assert o == 5   # Overridden value


# 1. Function with defaults (Schema)
@flexcli
def train(lr=0.01, epochs=10, save_dir='/tmp/flexlock_test'):
    return {"lr": lr, "epochs": epochs}

def test_py2cfg_defaults_and_overrides():
    """
    Test that function signature defaults are preserved and can be overridden.
    This validates the 'implicit schema' philosophy.
    """
    

    # Case A: Run with defaults (No args)
    with mock_argv([]):
        res = train()
        assert res["lr"] == 0.01
        assert res["epochs"] == 10

    # Case B: Override via CLI (Inner overrides implicit root). Case A already
    # ran into the same save_dir, so an explicit policy is required to rerun
    # in place (the default guard would refuse).
    with mock_argv(["-O", "lr=0.05", "epochs=50", "--save-dir-policy", "unsafe"]):
        res = train()
        assert res["lr"] == 0.05
        assert res["epochs"] == 50


# --- Multi-stage selection (Phase 1) ---
#
# The target records call order to a *file* (not a module global): the
# `_target_` import can resolve to a different module instance than the one
# pytest loaded this test from, so a shared list wouldn't be observed.


def record_stage(name, save_dir, log, upstream=None):
    """Append this stage's name to a shared log file; assert the upstream
    stage's dir already exists on disk (the ordering guarantee)."""
    if upstream is not None:
        assert Path(upstream).exists(), f"upstream {upstream} not on disk yet"
    with open(log, "a") as fh:
        fh.write(name + "\n")
    return {"name": name}


def _pipeline_yaml(f):
    f.write(
        """
pipeline_dir: ???

stage_a:
  _target_: tests.test_multistage_config.record_stage
  name: a
  save_dir: ${pipeline_dir}/a
  log: ${pipeline_dir}/order.log

stage_b:
  _target_: tests.test_multistage_config.record_stage
  name: b
  save_dir: ${pipeline_dir}/b
  log: ${pipeline_dir}/order.log
  upstream: ${pipeline_dir}/a
"""
    )
    f.close()


def _read_order(tmp_path):
    log = tmp_path / "order.log"
    return log.read_text().split() if log.exists() else []


def test_multistage_runs_in_order(temp_yaml, tmp_path):
    """`-s stage_a stage_b` runs stages sequentially; downstream sees upstream."""
    from flexlock.runner import FlexLockRunner

    f, config_path = temp_yaml
    _pipeline_yaml(f)

    FlexLockRunner().run(
        cli_args=[
            "-c", str(config_path),
            "-s", "stage_a", "stage_b",
            "-o", f"pipeline_dir={tmp_path}",
        ]
    )

    assert _read_order(tmp_path) == ["a", "b"]
    assert (tmp_path / "a").exists()
    assert (tmp_path / "b").exists()


def test_multistage_comma_separated(temp_yaml, tmp_path):
    """Comma-separated `-s stage_a,stage_b` is equivalent to space-separated."""
    from flexlock.runner import FlexLockRunner

    f, config_path = temp_yaml
    _pipeline_yaml(f)

    FlexLockRunner().run(
        cli_args=[
            "-c", str(config_path),
            "-s", "stage_a,stage_b",
            "-o", f"pipeline_dir={tmp_path}",
        ]
    )

    assert _read_order(tmp_path) == ["a", "b"]


def test_multistage_rejects_after_select_override(temp_yaml, tmp_path):
    """-O targets a single node — ambiguous with a stage sequence."""
    from flexlock.runner import FlexLockRunner
    from flexlock.exceptions import FlexLockValidationError

    f, config_path = temp_yaml
    _pipeline_yaml(f)

    with pytest.raises(FlexLockValidationError):
        FlexLockRunner().run(
            cli_args=[
                "-c", str(config_path),
                "-s", "stage_a", "stage_b",
                "-o", f"pipeline_dir={tmp_path}",
                "-O", "name=x",
            ]
        )


def test_multistage_composes_with_sweep(temp_yaml, tmp_path):
    """-s a b --sweep merges each item at the root pre-selection, then runs
    one composite pipeline task per item (stages in order)."""
    from flexlock.runner import FlexLockRunner

    f, config_path = temp_yaml
    _pipeline_yaml(f)
    root1 = tmp_path / "xp1"
    root2 = tmp_path / "xp2"
    FlexLockRunner().run(
        cli_args=[
            "-c", str(config_path),
            "-s", "stage_a", "stage_b",
            "--sweep-target", "pipeline_dir",
            "--sweep", f"{root1},{root2}",
        ]
    )

    for root in (root1, root2):
        assert _read_order(root) == ["a", "b"]
        assert (root / "a").exists()
        assert (root / "b").exists()


def test_multistage_rejects_after_select_merge(temp_yaml, tmp_path):
    """-M targets a single node — still ambiguous with a stage sequence."""
    from flexlock.runner import FlexLockRunner
    from flexlock.exceptions import FlexLockValidationError

    f, config_path = temp_yaml
    _pipeline_yaml(f)
    mfile = tmp_path / "m.yaml"
    mfile.write_text("name: x\n")

    with pytest.raises(FlexLockValidationError):
        FlexLockRunner().run(
            cli_args=[
                "-c", str(config_path),
                "-s", "stage_a", "stage_b",
                "-o", f"pipeline_dir={tmp_path}",
                "-M", str(mfile),
            ]
        )


def test_single_select_unchanged(temp_yaml, tmp_path):
    """A single `-s stage_a` still runs exactly one stage (back-compat)."""
    from flexlock.runner import FlexLockRunner

    f, config_path = temp_yaml
    _pipeline_yaml(f)

    FlexLockRunner().run(
        cli_args=[
            "-c", str(config_path),
            "-s", "stage_a",
            "-o", f"pipeline_dir={tmp_path}",
        ]
    )

    assert _read_order(tmp_path) == ["a"]


def test_context_preservation_sanity():
    """
    Direct OmegaConf sanity check to ensure the library behavior 
    matches our assumptions about selection and parent pointers.
    """
    yaml_content = """
    root_val: 100
    level1:
        val: ${root_val}
        level2:
            val: ${root_val}
    """
    cfg = OmegaConf.create(yaml_content)

    # 1. Select level1.level2
    # Note: OmegaConf.select preserves the parent graph by default
    node = OmegaConf.select(cfg, "level1.level2")
    
    assert node.val == 100
    
    # 2. Modify root, ensure node updates (dynamic interpolation)
    cfg.root_val = 200
    assert node.val == 200

    # 3. Ensure converting to container resolves correctly
    container = OmegaConf.to_container(node, resolve=True)
    assert container["val"] == 200


def test_multistage_dump_iterates_items_and_stages(temp_yaml, tmp_path, capsys):
    """--dump over -s a b --sweep prints each item × stage with headers and
    each sweep item's root merge reaches the stage save_dir."""
    from flexlock.runner import FlexLockRunner

    f, config_path = temp_yaml
    _pipeline_yaml(f)
    FlexLockRunner().run(
        cli_args=[
            "-c", str(config_path),
            "-s", "stage_a", "stage_b",
            "--sweep-target", "pipeline_dir",
            "--sweep", f"{tmp_path}/xp1,{tmp_path}/xp2",
            "--dump",
        ]
    )
    out = capsys.readouterr().out
    assert "# --- item 0 / stage: stage_a ---" in out
    assert "# --- item 1 / stage: stage_b ---" in out
    # Per-item root merge reached each stage save_dir.
    assert f"{tmp_path}/xp1/a" in out
    assert f"{tmp_path}/xp2/b" in out


def test_multistage_enqueue_writes_composite_tasks(temp_yaml, tmp_path):
    """-s a b --enqueue twice with different pipeline_dir → 2 composite entries."""
    import yaml as _yaml
    from flexlock.runner import FlexLockRunner

    f, config_path = temp_yaml
    _pipeline_yaml(f)
    q = tmp_path / "queue.yaml"

    for name in ("xp1", "xp2"):
        FlexLockRunner().run(
            cli_args=[
                "-c", str(config_path),
                "-s", "stage_a", "stage_b",
                "-o", f"pipeline_dir={tmp_path}/{name}",
                "--enqueue", str(q),
            ]
        )

    data = _yaml.safe_load(q.read_text())
    assert len(data) == 2
    assert all("_stages_" in d for d in data)
    assert len(data[0]["_stages_"]) == 2
    assert data[0]["_stages_"][0]["save_dir"] == f"{tmp_path}/xp1/a"
    assert data[1]["_stages_"][1]["save_dir"] == f"{tmp_path}/xp2/b"
