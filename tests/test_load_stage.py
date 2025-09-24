import pytest
from pathlib import Path
import yaml
from omegaconf import OmegaConf
from dataclasses import dataclass

from naga.load_stage import load_stage
from naga.context import run_context

@pytest.fixture
def nested_stages(tmp_path):
    """Creates a nested dependency chain of runs: C -> B -> A."""
    # Stage A (no dependencies)
    dir_a = tmp_path / "stage_A"
    dir_a.mkdir()
    data_a = {"config": {"save_dir": str(dir_a)}, "result": "A"}
    with open(dir_a / "run.lock", 'w') as f:
        yaml.dump(data_a, f)

    # Stage B (depends on A)
    dir_b = tmp_path / "stage_B"
    dir_b.mkdir()
    data_b = {
        "config": {"save_dir": str(dir_b)},
        "result": "B",
        "previous_stages": {"stage_a": data_a}
    }
    with open(dir_b / "run.lock", 'w') as f:
        yaml.dump(data_b, f)

    # Stage C (depends on B)
    dir_c = tmp_path / "stage_C"
    dir_c.mkdir()
    data_c = {
        "config": {"save_dir": str(dir_c)},
        "result": "C",
        "previous_stages": {"stage_b": data_b}
    }
    with open(dir_c / "run.lock", 'w') as f:
        yaml.dump(data_c, f)
        
    return dir_a, dir_b, dir_c

def test_flattening_and_deduplication(nested_stages):
    """Test that the decorator correctly flattens the dependency tree."""
    dir_a, dir_b, dir_c = nested_stages

    @dataclass
    class MyConfig:
        # Direct dependencies of the new run
        stage_c_path: str = str(dir_c)
        stage_b_path: str = str(dir_b) # Add a redundant dependency

    @load_stage("stage_c_path", "stage_b_path")
    def my_function(cfg: MyConfig):
        pass

    # Reset context for a clean test
    run_context.set({})
    
    cfg = OmegaConf.structured(MyConfig)
    my_function(cfg)

    context_data = run_context.get()
    previous_stages = context_data.get("previous_stages", {})

    # 1. Check that all ancestors are present at the top level
    assert str(dir_a) in previous_stages
    assert str(dir_b) in previous_stages
    assert str(dir_c) in previous_stages # Loaded via stage_b from stage_c

    # 2. Check that the data is correct and flattened (no nested previous_stages)
    assert previous_stages[str(dir_c)]["result"] == "C"
    assert "previous_stages" not in previous_stages[str(dir_c)]

    assert previous_stages[str(dir_b)]["result"] == "B"
    assert "previous_stages" not in previous_stages[str(dir_b)]
    
    assert previous_stages[str(dir_a)]["result"] == "A"
    assert "previous_stages" not in previous_stages[str(dir_a)]

    # 3. Check that the number of keys is exactly 3 (deduplication worked)
    print(OmegaConf.to_yaml(previous_stages))
    assert len(previous_stages) == 3
