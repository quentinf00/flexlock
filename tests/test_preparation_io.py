"""Bounded preparation I/O completes under controller ownership before dispatch."""
from collections import Counter
from pathlib import Path
import json
import threading

import pytest
from flexlock import destination_guard as guard
from flexlock.exceptions import FlexLockValidationError
from flexlock.taskdb import queue_tasks


@pytest.fixture(params=[1, 2, 4])
def workers(request, monkeypatch):
    monkeypatch.setattr(guard, '_IO_WORKERS', request.param)
    return request.param


def test_shared_ancestors_are_probed_once(tmp_path, monkeypatch, workers):
    seen = Counter()
    original = guard._existing_database
    def probe(path):
        seen[str(path)] += 1
        return original(path)
    monkeypatch.setattr(guard, '_existing_database', probe)
    products = [tmp_path/'products'/str(i) for i in range(20)]
    with guard.guard_destinations(products):
        pass
    assert seen[str(tmp_path/'products'/'run.lock.tasks.db')] == 1
    assert all(count == 1 for count in seen.values())
    assert all(seen[str(p/'run.lock.tasks.db')] == 1 for p in products)


def test_ancestor_queue_still_blocks_before_body(tmp_path, workers):
    product = tmp_path/'legacy'/'nested'/'product'
    queue_tasks(tmp_path/'legacy'/'run.lock.tasks.db', [dict(save_dir=str(product))])
    with pytest.raises(FlexLockValidationError, match='pending/running'):
        with guard.guard_destinations([product]):
            pytest.fail('guard body must not start')


def test_reservations_deduplicate_aliases_and_finish_before_return(tmp_path, workers):
    product = tmp_path/'product'
    guard.reserve_queue([product, product/'../product', str(product)], tmp_path/'queue.db')
    assert json.loads((product/guard.QUEUE_POINTER).read_text()) == dict(task_db=str(tmp_path/'queue.db'))
    assert not list(product.glob('*.tmp'))


@pytest.mark.parametrize('operation', ['preflight', 'reservation'])
def test_failed_io_joins_other_operations_before_releasing_locks(tmp_path, monkeypatch, workers, operation):
    if workers == 1:
        pytest.skip('join ordering requires concurrent I/O')
    a, b = tmp_path/'a', tmp_path/'b'
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    errors = []
    original_probe, original_write = guard._product_databases, guard._write_reservation
    def operation_body(path, payload=None):
        path = Path(path)
        if path == a:
            assert started.wait(5)
            raise OSError('injected I/O failure')
        if path == b:
            started.set()
            assert release.wait(5)
        return original_probe(path) if payload is None else original_write(path, payload)
    with monkeypatch.context() as patch:
        patch.setattr(guard, '_product_databases' if operation == 'preflight' else '_write_reservation', operation_body)
        def invoke():
            try:
                with guard.guard_destinations([a, b]):
                    guard.reserve_queue([a, b], tmp_path/'queue.db')
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()
        thread = threading.Thread(target=invoke)
        thread.start()
        try:
            assert started.wait(5)
            assert not finished.is_set()
            # Failure must not release ownership while another operation runs.
            with pytest.raises(FlexLockValidationError, match='another controller'):
                with guard.guard_destinations([a]):
                    pass
        finally:
            release.set()
            thread.join(5)
        assert not thread.is_alive() and finished.is_set()
        assert len(errors) == 1 and isinstance(errors[0], OSError)
    with guard.guard_destinations([a]):
        pass


def test_reservation_failure_prevents_scheduler_submission(tmp_path, monkeypatch, workers):
    from unittest.mock import MagicMock
    from omegaconf import OmegaConf
    from flexlock.api import Project
    backend = MagicMock()
    monkeypatch.setattr('flexlock.parallel.SlurmBackend', lambda **kw: backend)
    def fail(*args):
        raise OSError('injected reservation failure')
    monkeypatch.setattr(guard, '_write_reservation', fail)
    cfg = OmegaConf.create(dict(_target_='tests.test_save_dir_guard.guard_stage',
        save_dir=str(tmp_path/'products'), value=1,
        _snapshot_=dict(discover=dict(repos=False, prevs=False))))
    profile = tmp_path/'slurm.yaml'
    profile.write_text('startup_lines: []\n')
    with pytest.raises(OSError, match='injected reservation failure'):
        Project().submit(cfg, sweep=[dict(value=1,save_dir=str(tmp_path/'products/a')),
                                  dict(value=2,save_dir=str(tmp_path/'products/b'))],
                         slurm_config=str(profile), smart_run=False, wait=False)
    backend.submit.assert_not_called()
