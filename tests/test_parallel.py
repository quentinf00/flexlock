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
    return OmegaConf.create({"save_dir": str(save_dir), "task_id": 1, "worker_id": ""})


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
        task_target=".",  # Merge task dict into the root of the config
        cfg=base_cfg,
        n_jobs=2,
    )
    success = executor.run()
    logger.info(executor.db_path)

    # Should return True for successful execution
    assert success is True

    # Verify that the final results file was created
    results_file = Path(base_cfg.save_dir) / "run.lock.tasks"
    assert results_file.exists()

    with open(results_file, "r") as f:
        results = yaml.safe_load(f)

    assert len(results) == 4
    assert all(item["status"] == "done" for item in results)
    # Check that task IDs from 0 to 3 are present
    assert {item["task"]["task"] for item in results} == {0, 1, 2, 3}


def test_executor_handles_no_tasks(base_cfg):
    """Tests that the executor exits gracefully when given an empty task list."""
    results_file = Path(base_cfg.save_dir) / "run.lock.tasks"
    executor = ParallelExecutor(
        func=dummy_task_func, tasks=[], task_target=".", cfg=base_cfg, n_jobs=1
    )
    logger.info(executor.db_path)
    executor.run()
    # The results file should still be created, but it should be empty
    results_file = Path(base_cfg.save_dir) / "run.lock.tasks"
    assert results_file.exists()
    assert results_file.read_text().strip() in ["[]", ""]


@patch("flexlock.parallel.SlurmBackend")
def test_executor_selects_slurm_backend(mock_slurm_backend, base_cfg, tmp_path):
    """Verify that providing a slurm_config instantiates the SlurmBackend."""
    slurm_config_path = tmp_path / "slurm.yaml"
    slurm_config_path.write_text("partition: 'test'")

    tasks = [{"task_id": 1}]
    executor = ParallelExecutor(
        func=dummy_task_func,
        tasks=tasks,
        task_target=".",
        cfg=base_cfg,
        slurm_config=str(slurm_config_path),
    )
    # Don't wait - just test that backend is instantiated and called
    executor.run(wait=False)

    mock_slurm_backend.assert_called_once()
    # Check that the backend's map_array or submit method was called
    backend_instance = mock_slurm_backend.return_value
    assert backend_instance.submit.called or backend_instance.map_array.called


@patch("flexlock.parallel.PBSBackend")
def test_executor_selects_pbs_backend(mock_pbs_backend, base_cfg, tmp_path):
    """Verify that providing a pbs_config instantiates the PBSBackend."""
    pbs_config_path = tmp_path / "pbs.yaml"
    pbs_config_path.write_text("queue: 'default'")

    tasks = [{"task_id": 1}]
    executor = ParallelExecutor(
        func=dummy_task_func,
        tasks=tasks,
        task_target=".",
        cfg=base_cfg,
        pbs_config=str(pbs_config_path),
    )
    # Don't wait - just test that backend is instantiated and called
    executor.run(wait=False)

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
        func=failing_func, tasks=tasks, task_target=".", cfg=base_cfg, n_jobs=1
    )
    success = executor.run()

    # Should return False because one task failed
    assert success is False

    # Check the database state directly via the dump function
    db_path = Path(base_cfg.save_dir) / "run.lock.tasks.db"

    from flexlock.taskdb import _conn

    with _conn(executor.db_path) as c:
        # Check task 0 (success)
        success_task = c.execute(
            "SELECT status, error, result_info FROM tasks WHERE task_info LIKE '%task_id: 0%'"
        ).fetchone()
        assert success_task[0] == "done"
        assert success_task[1] is None

        # Check task 1 (failure)
        failed_task = c.execute(
            "SELECT status, error, result_info FROM tasks WHERE task_info LIKE '%task_id: 1%'"
        ).fetchone()
        assert failed_task[0] == "failed"
        assert "This task is designed to fail" in failed_task[1]
        assert failed_task[2] is None


def test_wait_parameter_with_local_execution(base_cfg):
    """Tests that wait parameter works correctly with local execution."""
    tasks = [{"task_id": i, "worker_id": "local"} for i in range(4)]

    executor = ParallelExecutor(
        func=dummy_task_func,
        tasks=tasks,
        task_target=".",
        cfg=base_cfg,
        n_jobs=2,
    )

    # Local execution always completes synchronously, wait is implicit
    success = executor.run(wait=True)
    assert success is True

    # Verify all tasks completed
    from flexlock.taskdb import get_status_counts
    counts = get_status_counts(executor.db_path)
    assert counts.get('done', 0) == 4
    assert counts.get('pending', 0) == 0
    assert counts.get('running', 0) == 0


@patch("flexlock.parallel.PBSBackend")
def test_wait_parameter_with_hpc_backend(mock_pbs_backend, base_cfg, tmp_path):
    """Tests that wait parameter is passed correctly to HPC backends."""
    pbs_config_path = tmp_path / "pbs.yaml"
    pbs_config_path.write_text("queue: 'default'")

    # Mock the backend submission
    mock_job = MagicMock()
    mock_job.job_id = "12345"
    mock_backend_instance = mock_pbs_backend.return_value
    mock_backend_instance.submit.return_value = mock_job

    tasks = [{"task_id": 1}]
    executor = ParallelExecutor(
        func=dummy_task_func,
        tasks=tasks,
        task_target=".",
        cfg=base_cfg,
        pbs_config=str(pbs_config_path),
    )

    # Mock _wait_for_completion to immediately return True
    with patch.object(executor, '_wait_for_completion', return_value=True) as mock_wait:
        success = executor.run(wait=True, timeout=60)

        # Verify wait was called with correct parameters (default poll_interval=10)
        mock_wait.assert_called_once_with(60, None)
        assert success is True


@patch("flexlock.parallel.PBSBackend")
def test_no_wait_returns_immediately(mock_pbs_backend, base_cfg, tmp_path):
    """Tests that wait=False returns immediately without blocking."""
    pbs_config_path = tmp_path / "pbs.yaml"
    pbs_config_path.write_text("queue: 'default'")

    # Mock the backend
    mock_job = MagicMock()
    mock_job.job_id = "12345"
    mock_backend_instance = mock_pbs_backend.return_value
    mock_backend_instance.submit.return_value = mock_job

    tasks = [{"task_id": 1}]
    executor = ParallelExecutor(
        func=dummy_task_func,
        tasks=tasks,
        task_target=".",
        cfg=base_cfg,
        pbs_config=str(pbs_config_path),
    )

    # Mock _wait_for_completion (should NOT be called)
    with patch.object(executor, '_wait_for_completion') as mock_wait:
        success = executor.run(wait=False)

        # Verify wait was NOT called
        mock_wait.assert_not_called()
        assert success is True


def test_status_helper_functions(base_cfg):
    """Tests the new status helper functions in taskdb."""
    from flexlock.taskdb import get_status_counts, get_failed_tasks, get_all_tasks

    def failing_func(cfg):
        if cfg.task_id == 1:
            raise ValueError("Task 1 failed")
        return {"task": cfg.task_id, "status": "completed"}

    tasks = [{"task_id": 0}, {"task_id": 1}, {"task_id": 2}]

    executor = ParallelExecutor(
        func=failing_func, tasks=tasks, task_target=".", cfg=base_cfg, n_jobs=1
    )
    executor.run()

    # Test get_status_counts
    counts = get_status_counts(executor.db_path)
    assert counts.get('done', 0) == 2
    assert counts.get('failed', 0) == 1
    assert counts.get('pending', 0) == 0

    # Test get_failed_tasks
    failed = get_failed_tasks(executor.db_path)
    assert len(failed) == 1
    assert "Task 1 failed" in failed[0]['error']
    assert failed[0]['task']['task_id'] == 1

    # Test get_all_tasks
    all_tasks = get_all_tasks(executor.db_path)
    assert len(all_tasks) == 3

    # Test filtering by status
    failed_only = get_all_tasks(executor.db_path, status='failed')
    assert len(failed_only) == 1
    assert failed_only[0]['status'] == 'failed'

    done_only = get_all_tasks(executor.db_path, status='done')
    assert len(done_only) == 2
    assert all(t['status'] == 'done' for t in done_only)


def test_keyboard_interrupt_handling():
    """Test that KeyboardInterrupt is handled gracefully during wait."""
    from flexlock.parallel import ParallelExecutor
    from omegaconf import OmegaConf
    from pathlib import Path
    import tempfile
    from unittest.mock import patch
    
    # Create a temporary directory for the test
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = OmegaConf.create({
            'save_dir': tmpdir,
            'model': 'test'
        })
        
        def dummy_func(cfg):
            return cfg.model
        
        executor = ParallelExecutor(
            func=dummy_func,
            tasks=[{'param': 1}],
            task_target='.',
            cfg=cfg,
            n_jobs=1
        )
        
        # Mock time.sleep to raise KeyboardInterrupt
        with patch('time.sleep', side_effect=KeyboardInterrupt()):
            success = executor._wait_for_completion(timeout=None)
            
        # Should return False and not raise the exception
        assert success is False


def test_config_constants_used():
    """Test that config constants are used for defaults."""
    from flexlock.parallel import ParallelExecutor
    from flexlock import config
    from omegaconf import OmegaConf
    from pathlib import Path
    import tempfile
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = OmegaConf.create({
            'save_dir': tmpdir,
            'model': 'test'
        })
        
        def dummy_func(cfg):
            return cfg.model
        
        executor = ParallelExecutor(
            func=dummy_func,
            tasks=[],
            task_target='.',
            cfg=cfg,
            n_jobs=1
        )
        
        # Test that run() accepts None for poll_interval (uses config default)
        # We can't easily test the actual value without running the executor,
        # but we can verify the method signature accepts None
        import inspect
        sig = inspect.signature(executor.run)
        assert sig.parameters['poll_interval'].default is None
        
        # Test _wait_for_completion also accepts None
        sig2 = inspect.signature(executor._wait_for_completion)
        assert sig2.parameters['poll_interval'].default is None
