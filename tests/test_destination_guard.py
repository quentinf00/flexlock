"""Controller collisions are rejected before mutation or backend submission."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import threading

import pytest
from omegaconf import OmegaConf
from flexlock.api import Project
from flexlock.destination_guard import guard_destinations, CONTROLLER_LOCK
from flexlock.exceptions import FlexLockValidationError
from flexlock.taskdb import queue_tasks


def cfg(path, value=1):
    return OmegaConf.create(dict(_target_='tests.test_save_dir_guard.guard_stage',
                                save_dir=str(path), value=value))


@pytest.fixture
def backend(tmp_path, monkeypatch):
    backend = MagicMock()
    backend.submit.return_value = SimpleNamespace(job_id='123')
    monkeypatch.setattr('flexlock.parallel.SlurmBackend', lambda **kwargs: backend)
    profile = tmp_path/'slurm.yaml';profile.write_text('startup_lines: ["#SBATCH --hold"]\n')
    return backend, str(profile)


@pytest.mark.parametrize('policy', [None, 'overwrite', 'unsafe'])
def test_pending_held_submission_cannot_be_forced(tmp_path, backend, policy):
    stub, profile = backend
    directory = tmp_path/'run';project = Project()
    project.submit(cfg(directory),  slurm_config=profile, wait=False)
    assert stub.submit.call_count == 1
    before = (directory/'run.lock').read_bytes()
    # Even a stale completion marker must survive a refused forced launch.
    complete = directory/'run.complete';complete.write_text('old')
    with pytest.raises(FlexLockValidationError, match='pending/running'):
        project.submit(cfg(directory, 2),  slurm_config=profile,
                       force=True, save_dir_policy=policy, wait=False)
    assert stub.submit.call_count == 1
    assert (directory/'run.lock').read_bytes() == before
    assert complete.read_text() == 'old'


def test_remote_campaign_reserves_product_before_worker_start(tmp_path, backend):
    stub, profile = backend
    product = tmp_path/'products/one';queue = tmp_path/'queues/campaign'
    project = Project()
    project.submit(cfg(product), sweep=[dict(value=1)], sweep_root=str(queue),
                    slurm_config=profile, wait=False)
    assert not (product/'run.lock').exists()
    with pytest.raises(FlexLockValidationError, match='pending/running'):
        project.submit(cfg(product, 2), force=True, slurm_config=profile, wait=False)
    assert stub.submit.call_count == 1


def test_batch_refusal_preserves_earlier_product(tmp_path, backend):
    stub, profile = backend
    first = tmp_path/'products/first';second = tmp_path/'products/second'
    Project().submit(cfg(first))
    before = (first/'run.lock').read_bytes()
    db = tmp_path/'queues/active/run.lock.tasks.db'
    queue_tasks(db, [cfg(second)])
    from flexlock.destination_guard import reserve_queue
    reserve_queue([second], db)
    with pytest.raises(FlexLockValidationError, match='pending/running'):
        Project().submit(cfg(first), sweep=[dict(save_dir=str(first)), dict(save_dir=str(second))],
                         sweep_root=str(tmp_path/'newqueue'), force=True,
                         save_dir_policy='overwrite', slurm_config=profile, wait=False)
    assert (first/'run.lock').read_bytes() == before
    assert (first/'run.complete').exists()
    stub.submit.assert_not_called()


def test_other_controller_refused_and_lock_inode_survives_cleaning(tmp_path):
    destination = tmp_path/'run'
    errors = []
    with guard_destinations([destination]):
        def attempt():
            try:
                Project().submit(cfg(destination), force=True)
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=attempt);thread.start();thread.join(timeout=5)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], FlexLockValidationError)
        (destination/'run.lock').write_text('old')
        inode = (destination/CONTROLLER_LOCK).stat().st_ino
        from flexlock.save_dir import clean_run_dir
        clean_run_dir(destination)
        assert (destination/CONTROLLER_LOCK).stat().st_ino == inode


@pytest.mark.parametrize('sweep', [False, True])
def test_force_dry_run_preserves_record_and_completion(tmp_path, backend, sweep):
    stub, profile = backend
    destination = tmp_path/'run';Project().submit(cfg(destination))
    before = {p.name: p.read_bytes() for p in destination.iterdir() if p.is_file()}
    Project().submit(cfg(destination), sweep=[dict(value=2)] if sweep else None,
                     slurm_config=profile, force=True, dry_run=True)
    assert {p.name: p.read_bytes() for p in destination.iterdir() if p.is_file()} == before
    stub.submit.assert_not_called()


def test_forced_replacement_cannot_be_found_under_old_fingerprint(tmp_path, monkeypatch):
    from flexlock import index
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'index.db'))
    destination = tmp_path/'run';project = Project()
    project.submit(cfg(destination, 1))
    import yaml
    old = yaml.safe_load((destination/'run.lock').read_text())['fingerprint']
    # Explicit maintenance indexing remains available; submission no longer publishes it.
    index.record_run_lock(destination, old)
    old_row = index.lookup(tmp_path, old)
    assert old_row is not None
    project.submit(cfg(destination, 2), force=True)
    assert index.verify_and_resolve(tmp_path, old_row) is None


@pytest.mark.parametrize('state', ['pending', 'running'])
def test_pipeline_active_refusal_preserves_every_completion(tmp_path, backend, state):
    from flexlock.taskdb import claim_next_task
    stub, profile = backend
    root = tmp_path/'chain';a = cfg(root/'a');b = cfg(root/'b')
    Project().submit(a);Project().submit(b)
    db = root/'run.lock.tasks.db'
    queue_tasks(db, [dict(_stages_=[dict(a), dict(b)])])
    if state == 'running':
        claim_next_task(db, 'test-node')
    before = {str(path): path.read_bytes() for path in root.rglob('run.complete')}
    with pytest.raises(FlexLockValidationError, match='pending/running'):
        Project().submit_pipeline([[a, b]], force=True, slurm_config=profile, wait=False)
    assert {str(path): path.read_bytes() for path in root.rglob('run.complete')} == before
    stub.submit.assert_not_called()


def test_disjoint_append_cannot_replace_active_queue_master(tmp_path, backend):
    stub, profile = backend
    queue = tmp_path/'campaign';project = Project()
    kwargs = dict(sweep=[dict(value=1)], sweep_root=str(queue),
                  slurm_config=profile,  wait=False)
    project.submit(cfg(tmp_path/'products/a'), **kwargs)
    before = (queue/'run.lock').read_bytes()
    with pytest.raises(FlexLockValidationError, match='pending/running'):
        project.submit(cfg(tmp_path/'products/b'), **kwargs)
    assert (queue/'run.lock').read_bytes() == before
    assert stub.submit.call_count == 1


def test_force_hpc_to_local_replacement_removes_stale_worker_reference(tmp_path, backend, monkeypatch):
    from flexlock.record import load_record, MARKER_NAME
    from flexlock.destination_guard import QUEUE_POINTER
    monkeypatch.setattr('flexlock.worker.time.sleep', lambda _: None)
    stub, profile = backend
    directory = tmp_path/'run';project = Project()
    project.submit(cfg(directory, 1), slurm_config=profile, wait=False)
    args, kwargs = stub.submit.call_args
    args[0](*args[1:], **kwargs)
    assert load_record(directory)['config']['value'] == 1
    result = project.submit(cfg(directory, 2), force=True)
    assert result.status == 'SUCCESS'
    assert load_record(directory)['config']['value'] == 2
    assert not (directory/MARKER_NAME).exists()
    assert not (directory/QUEUE_POINTER).exists()
    assert not (directory/'run.lock.tasks.db').exists()


@pytest.mark.parametrize('state', ['failed', 'interrupted'])
@pytest.mark.parametrize('isolated', [False, True])
def test_single_queued_failure_never_reports_success(tmp_path, monkeypatch, state, isolated):
    from flexlock.taskdb import finish_task
    directory = tmp_path/'run'
    def executor(**kwargs):
        db = directory/'run.lock.tasks.db'
        queue_tasks(db, kwargs['tasks'], tag='failure')
        finish_task(db, kwargs['tasks'][0], error='retained failure', status=state)
        return SimpleNamespace(db_path=db, tag='failure', job=None, run=lambda **kw: False)
    monkeypatch.setattr('flexlock.parallel.ParallelExecutor', executor)
    kwargs = dict(isolated=True) if isolated else dict(slurm_config='unused.yaml')
    result = Project().submit(cfg(directory),  **kwargs)
    assert result.status == state.upper()
    assert not result.is_success


def test_local_callable_without_record_destination_creates_no_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = Project().submit(dict(_target_='tests.test_api.dummy_func', a=1, b=2))
    assert result.status == 'SUCCESS' and result.result['sum'] == 3
    assert list(tmp_path.iterdir()) == []
