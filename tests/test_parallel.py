
import pytest
from naga.parallel import load_tasks, merge_task_into_cfg, ParallelExecutor
from omegaconf import OmegaConf
from pathlib import Path
import yaml

@pytest.fixture
def tasks_txt_file(tmp_path):
    file_path = tmp_path / "tasks.txt"
    file_path.write_text("task1\ntask2\ntask3")
    return str(file_path)

@pytest.fixture
def tasks_yaml_file(tmp_path):
    file_path = tmp_path / "tasks.yaml"
    with file_path.open("w") as f:
        yaml.dump([{"id": 1, "param": "a"}, {"id": 2, "param": "b"}], f)
    return str(file_path)

@pytest.fixture
def base_cfg():
    return OmegaConf.create({
        "experiment": {
            "tasks": ["task_from_cfg_1", "task_from_cfg_2"]
        },
        "save_dir": "/tmp/test_save_dir"
    })

def test_load_tasks_from_txt(tasks_txt_file):
    tasks = load_tasks(tasks_txt_file, None, OmegaConf.create())
    assert tasks == ["task1", "task2", "task3"]

def test_load_tasks_from_yaml(tasks_yaml_file):
    tasks = load_tasks(tasks_yaml_file, None, OmegaConf.create())
    assert tasks == [{"id": 1, "param": "a"}, {"id": 2, "param": "b"}]

def test_load_tasks_from_cfg(base_cfg):
    tasks = load_tasks(None, "experiment.tasks", base_cfg)
    assert tasks == ["task_from_cfg_1", "task_from_cfg_2"]

def test_load_tasks_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_tasks("non_existent_file.txt", None, OmegaConf.create())

def test_merge_task_into_cfg():
    cfg = OmegaConf.create({"a": {"b": 1}})
    task = {"c": 2}
    merged_cfg = merge_task_into_cfg(cfg, task, "a.task_data")
    assert merged_cfg.a.b == 1
    assert merged_cfg.a.task_data.c == 2

def test_parallel_executor_serial(base_cfg, tmp_path):
    call_count = 0
    def dummy_func(cfg):
        nonlocal call_count
        call_count += 1
        assert cfg.save_dir == str(tmp_path)

    base_cfg.save_dir = str(tmp_path)
    tasks = ["task1", "task2"]
    executor = ParallelExecutor(dummy_func, tasks, "task_id", base_cfg, 1, None)
    executor.run()
    assert call_count == 2

def test_parallel_executor_joblib(base_cfg, tmp_path):
    
    def dummy_func(cfg):
        # In a real scenario, this would do work.
        # For testing, we just check if the config is correct.
        assert "task_id" in cfg
        # create a file to signal that the task was run
        (Path(cfg.save_dir) / cfg.task_id).touch()

    base_cfg.save_dir = str(tmp_path)
    tasks = ["task1", "task2", "task3"]
    executor = ParallelExecutor(dummy_func, tasks, "task_id", base_cfg, n_jobs=2, slurm_config=None)
    executor.run()

    # Check that files were created for each task
    for task in tasks:
        assert (Path(base_cfg.save_dir) / task).exists()


def test_parallel_executor_skips_done_tasks(base_cfg, tmp_path):
    call_count = 0
    def dummy_func(cfg):
        nonlocal call_count
        call_count += 1

    base_cfg.save_dir = str(tmp_path)
    tasks = ["task1", "task2", "task3"]
    executor = ParallelExecutor(dummy_func, tasks, "task_id", base_cfg, 1, None)

    # Manually create a "done" file for task2
    done_file = executor._get_done_file_path("task2")
    done_file.parent.mkdir(exist_ok=True)
    done_file.touch()

    executor.run()
    assert call_count == 2 # Should only run task1 and task3

