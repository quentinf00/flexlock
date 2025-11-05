import pytest
from omegaconf import OmegaConf
from pathlib import Path
import yaml
from unittest.mock import patch, MagicMock
from loguru import logger
from flexlock.parallel import ParallelExecutor
logger.enable("flexlock")

@pytest.fixture
def base_cfg(tmp_path):
    """Provides a basic OmegaConf config with a save_dir."""
    save_dir = tmp_path / "test_run"
    save_dir.mkdir()
    return OmegaConf.create({
        "save_dir": str(save_dir),
        "task_id": 1,
        'worker_id': ""
    })

def dummy_task_func(cfg):
    """A simple function for tasks to execute, returns a result dict."""
    task_id = cfg.task_id
    return {"task": task_id, "status": "completed", "worker_id": cfg.worker_id}

def test_parallel_executor_local_execution(base_cfg):
    """
    Tests the full local execution pipeline:
    1. Tasks are queued in the database.
    2. The executor runs them locally using multiprocessing.
    3. The final results are dumped to a YAML file.
    """
    tasks = [{"task_id": i, "worker_id": "local"} for i in range(4)]
    
    executor = ParallelExecutor(
        func=dummy_task_func,
        tasks=tasks,
        task_to=".",  # Merge task dict into the root of the config
        cfg=base_cfg,
        n_jobs=2
    )
    executor.run()
    logger.info(executor.db_path)
    # Verify that the final results file was created
    results_file = Path(base_cfg.save_dir) / "run.lock.tasks"
    assert results_file.exists()

    with open(results_file, 'r') as f:
        results = yaml.safe_load(f)
    
    assert len(results) == 4
    assert all(item["status"] == "completed" for item in results)
    # Check that task IDs from 0 to 3 are present
    assert {item["task"] for item in results} == {0, 1, 2, 3}

def test_executor_handles_no_tasks(base_cfg):
    """Tests that the executor exits gracefully when given an empty task list."""
    results_file = Path(base_cfg.save_dir) / "run.lock.tasks"
    executor = ParallelExecutor(
        func=dummy_task_func,
        tasks=[],
        task_to=".",
        cfg=base_cfg,
        n_jobs=1
    )
    logger.info(executor.db_path)
    executor.run()
    # The results file should still be created, but it should be empty
    results_file = Path(base_cfg.save_dir) / "run.lock.tasks"
    assert results_file.exists()
    assert results_file.read_text().strip() in ["[]", ""]

@patch('flexlock.parallel.SlurmBackend')
def test_executor_selects_slurm_backend(mock_slurm_backend, base_cfg, tmp_path):
    """Verify that providing a slurm_config instantiates the SlurmBackend."""
    slurm_config_path = tmp_path / "slurm.yaml"
    slurm_config_path.write_text("partition: 'test'")
    
    tasks = [{"task_id": 1}]
    executor = ParallelExecutor(
        func=dummy_task_func,
        tasks=tasks,
        task_to=".",
        cfg=base_cfg,
        slurm_config=str(slurm_config_path)
    )
    executor.run()

    mock_slurm_backend.assert_called_once()
    # Check that the backend's map_array or submit method was called
    backend_instance = mock_slurm_backend.return_value
    assert backend_instance.submit.called or backend_instance.map_array.called

@patch('flexlock.parallel.PBSBackend')
def test_executor_selects_pbs_backend(mock_pbs_backend, base_cfg, tmp_path):
    """Verify that providing a pbs_config instantiates the PBSBackend."""
    pbs_config_path = tmp_path / "pbs.yaml"
    pbs_config_path.write_text("queue: 'default'")

    tasks = [{"task_id": 1}]
    executor = ParallelExecutor(
        func=dummy_task_func,
        tasks=tasks,
        task_to=".",
        cfg=base_cfg,
        pbs_config=str(pbs_config_path)
    )
    executor.run()

    mock_pbs_backend.assert_called_once()
    backend_instance = mock_pbs_backend.return_value
    assert backend_instance.submit.called or backend_instance.map_array.called

def test_task_failure_is_recorded(base_cfg):
    """Tests that if a task function raises an exception, it's handled and recorded."""
    
    def failing_func(cfg):
        if cfg.task_id == 1:
            raise ValueError("This task is designed to fail")
        return {"task": cfg.task_id, "status": "completed"}

    tasks = [{"task_id": 0}, {"task_id": 1}]
    
    # The executor should not raise an exception, but handle it gracefully
    executor = ParallelExecutor(
        func=failing_func,
        tasks=tasks,
        task_to=".",
        cfg=base_cfg,
        n_jobs=1
    )
    executor.run()

    # Check the database state directly via the dump function
    db_path = Path(base_cfg.save_dir) / "run.lock.tasks.db"
    
    from flexlock.taskdb import _conn
    with _conn(executor.db_path) as c:
        # Check task 0 (success)
        success_task = c.execute("SELECT status, error, result_info FROM tasks WHERE task_info LIKE 'task_id: 0%'").fetchone()
        assert success_task[0] == 'done'
        assert success_task[1] is None
        assert "status: completed" in success_task[2]

        # Check task 1 (failure)
        failed_task = c.execute("SELECT status, error, result_info FROM tasks WHERE task_info LIKE '%task_id: 1%'").fetchone()
        assert failed_task[0] == 'failed'
        assert "This task is designed to fail" in failed_task[1]
        assert failed_task[2] is None
