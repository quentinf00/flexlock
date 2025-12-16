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
    with mock_argv([
        "-c", str(config_path),
        "-s", "nested",
        "-O", "other=5" # Inner override
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

    # Case B: Override via CLI (Inner overrides implicit root)
    with mock_argv(["-O", "lr=0.05", "epochs=50"]):
        res = train()
        assert res["lr"] == 0.05
        assert res["epochs"] == 50


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
