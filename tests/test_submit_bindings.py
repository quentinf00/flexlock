"""Existing producers bind at dispatch; promised concrete paths bind at stage start."""
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from omegaconf import OmegaConf

from flexlock.api import Project
from flexlock.exceptions import FlexLockValidationError, WorkerExecutionError
from flexlock.record import load_record
from flexlock.resolvers import bind_existing_run_locks, resolve_deferred
from flexlock.run_record import RunRecord


def consume(save_dir, value):
    from pathlib import Path
    Path(save_dir, 'called').write_text(str(value))
    return value


def producer(path, value):
    path.mkdir(parents=True, exist_ok=True)
    RunRecord(path).write_lock({'config': {'value': value}, 'timestamp': '2026-10-07'})


def cfg(destination, source):
    return OmegaConf.create(dict(_target_='tests.test_submit_bindings.consume',
        save_dir=str(destination), value='${run_lock:'+str(source)+',config.value}',
        _snapshot_=dict(discover=dict(repos=False, prevs=False))))


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'index.db'))
    monkeypatch.setattr('flexlock.worker.time.sleep', lambda _: None)
    backend = MagicMock()
    backend.submit.return_value = SimpleNamespace(job_id='88')
    monkeypatch.setattr('flexlock.parallel.SlurmBackend', lambda **kw: backend)
    profile = tmp_path/'slurm.yaml'
    profile.write_text('startup_lines: []\n')
    return str(profile), backend


def run_submitted(backend):
    args, kwargs = backend.submit.call_args
    return args[0](*args[1:], **kwargs)


@pytest.mark.parametrize('dispatch', ['single', 'sweep', 'pipeline'])
@pytest.mark.parametrize('change', ['replace', 'remove', 'unchanged'])
@pytest.mark.parametrize('after', [False, True])
def test_existing_producer_is_frozen_and_checked_before_callable(tmp_path, scheduler, dispatch, change, after):
    profile, backend = scheduler
    source = tmp_path/'producer'
    producer(source, 41)
    destination = tmp_path/'consumer'
    config = cfg(destination, source)
    options = dict(slurm_config=profile, after=['77'] if after else None, wait=False, smart_run=False)
    if dispatch == 'single':
        Project().submit(config, **options)
    elif dispatch == 'sweep':
        Project().submit(config, sweep=[{}], **options)
    else:
        Project().submit_pipeline([[config]], **options)
    if change == 'replace':
        producer(source, 99)
    elif change == 'remove':
        (source/'run.lock').unlink()
    if change == 'unchanged':
        run_submitted(backend)
    else:
        with pytest.raises(WorkerExecutionError, match='failed task'):
            run_submitted(backend)
    if change == 'unchanged':
        assert (destination/'called').read_text() == '41'
        record = load_record(destination)
        assert record['run_lock_reads'][0]['binding'] == 'submit'
        assert record['lineage']['producer']['info']['config']['value'] == 41
    else:
        assert not (destination/'called').exists()
        assert not (destination/'run.complete').exists()
        from flexlock.taskdb import get_all_tasks
        from flexlock.queue_refs import ancestor_candidates, referenced_databases
        databases = referenced_databases(destination) | {
            db for db in ancestor_candidates([destination.resolve()]) if db.exists()}
        rows = [row for db in databases for row in get_all_tasks(db)]
        assert rows and all(row['status'] == 'failed' for row in rows)
        assert all('changed or disappeared after submission' in row['error'] for row in rows)


def test_missing_required_producer_without_after_fails_before_dispatch(tmp_path, scheduler):
    profile, backend = scheduler
    destination = tmp_path/'consumer'
    from omegaconf.errors import InterpolationResolutionError
    with pytest.raises(InterpolationResolutionError, match='no run.lock found'):
        Project().submit(cfg(destination, tmp_path/'missing'), slurm_config=profile, smart_run=False)
    backend.submit.assert_not_called()
    assert not destination.exists()


def test_promised_producer_with_after_uses_exact_path(tmp_path, scheduler):
    profile, backend = scheduler
    source = tmp_path/'promised'
    destination = tmp_path/'consumer'
    Project().submit(cfg(destination, source), slurm_config=profile, after=['77'], smart_run=False)
    producer(tmp_path/'newer', 99)
    producer(source, 41)
    run_submitted(backend)
    assert (destination/'called').read_text() == '41'
    record = load_record(destination)
    assert record['run_lock_reads'][0]['path'] == str(source)
    assert 'binding' not in record['run_lock_reads'][0]


def test_unchanged_binding_keeps_native_values_and_literal_interpolation(tmp_path):
    source = tmp_path/'producer'
    producer(source, ['literal ${not_a_config_key}', {'x': 3}])
    bound = bind_existing_run_locks(cfg(tmp_path/'consumer', source))
    resolved = resolve_deferred(bound)
    assert OmegaConf.to_container(resolved.value, resolve=True) == ['literal ${not_a_config_key}', {'x': 3}]


def test_missing_default_binds_default_and_detects_later_appearance(tmp_path):
    source = tmp_path/'producer'
    config = cfg(tmp_path/'consumer', source)
    config.value = '${run_lock:'+str(source)+',config.value,null}'
    bound = bind_existing_run_locks(config, allow_future=True)
    assert resolve_deferred(bound).value is None
    producer(source, 41)
    with pytest.raises(FlexLockValidationError, match='changed or disappeared'):
        resolve_deferred(bound)


def test_pipeline_typo_is_not_treated_as_promised_producer(tmp_path, scheduler):
    profile, backend = scheduler
    from omegaconf.errors import InterpolationResolutionError
    with pytest.raises(InterpolationResolutionError, match='no run.lock found'):
        Project().submit_pipeline([[cfg(tmp_path/'consumer', tmp_path/'typo')]],
            slurm_config=profile, smart_run=False)
    backend.submit.assert_not_called()
    assert not (tmp_path/'consumer').exists()


@pytest.mark.parametrize('nested', [False, True])
def test_latest_selection_is_fixed_when_newer_candidate_appears(tmp_path, scheduler, nested):
    import os
    profile, backend = scheduler
    first = tmp_path/'upstreams'/'A'
    producer(first, 41)
    os.utime(first, (1000000000, 1000000000))
    destination = tmp_path/'consumer'
    config = cfg(destination, first)
    choice = '${latest:'+str(first.parent/'*')+'}'
    config.value = '${run_lock:'+choice+',config.value}' if nested else choice
    Project().submit(config, slurm_config=profile, after=['77'], smart_run=False)
    producer(first.parent/'B', 99)
    run_submitted(backend)
    assert (destination/'called').read_text() == ('41' if nested else str(first))


def test_missing_promised_producer_stops_worker(tmp_path, scheduler):
    profile, backend = scheduler
    destination = tmp_path/'consumer'
    Project().submit(cfg(destination, tmp_path/'promised'), slurm_config=profile,
                     after=['77'], smart_run=False)
    with pytest.raises(WorkerExecutionError):
        run_submitted(backend)
    assert not (destination/'called').exists()
    assert not (destination/'run.complete').exists()


def test_existing_producer_missing_field_is_not_deferred(tmp_path, scheduler):
    from omegaconf.errors import InterpolationResolutionError
    profile, backend = scheduler
    source = tmp_path/'producer'
    producer(source, 41)
    config = cfg(tmp_path/'consumer', source)
    config.value = '${run_lock:'+str(source)+',config.typo}'
    with pytest.raises(InterpolationResolutionError, match="key 'config.typo' not found"):
        Project().submit(config, slurm_config=profile, after=['77'], smart_run=False)
    backend.submit.assert_not_called()
    assert not (tmp_path/'consumer').exists()


def test_queued_producer_without_dependency_fails_before_consumer_dispatch(tmp_path, scheduler):
    from omegaconf.errors import InterpolationResolutionError
    profile, backend = scheduler
    source = tmp_path/'producer'
    stage = cfg(source, source)
    stage.value = 41
    Project().submit(stage, slurm_config=profile, smart_run=False, wait=False)
    with pytest.raises(InterpolationResolutionError, match='pending/running work'):
        Project().submit(cfg(tmp_path/'consumer', source), slurm_config=profile, smart_run=False)
    assert backend.submit.call_count == 1
    assert not (tmp_path/'consumer').exists()


def test_pending_sibling_does_not_make_selected_producer_future(tmp_path, scheduler):
    from flexlock.destination_guard import reserve_queue
    from flexlock.taskdb import queue_tasks
    from flexlock.exceptions import WorkerExecutionError
    profile, backend = scheduler
    source = tmp_path/'producer'
    producer(source, 41)
    db = tmp_path/'queue'/'run.lock.tasks.db'
    db.parent.mkdir()
    queue_tasks(db, [dict(save_dir=str(tmp_path/'other'), x=1)])
    reserve_queue([source], db)
    destination = tmp_path/'consumer'
    Project().submit(cfg(destination, source), slurm_config=profile, after=['77'], smart_run=False)
    producer(source, 99)
    with pytest.raises(WorkerExecutionError):
        run_submitted(backend)
    assert not (destination/'called').exists()


def test_ordered_pipeline_defers_exact_earlier_stage_path(tmp_path, scheduler):
    profile, backend = scheduler
    first = tmp_path/'chain'/'a'
    second = tmp_path/'chain'/'b'
    prepare = cfg(first, first)
    prepare.value = 41
    Project().submit_pipeline([[prepare, cfg(second, first)]],
        slurm_config=profile, smart_run=False, wait=False)
    run_submitted(backend)
    assert (first/'called').read_text() == '41'
    assert (second/'called').read_text() == '41'
    assert load_record(second)['run_lock_reads'][0]['path'] == str(first)


def test_isolated_worker_rejects_replacement_and_returns_failed(tmp_path, monkeypatch):
    from flexlock.parallel import ParallelExecutor
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'index.db'))
    source = tmp_path/'producer'
    producer(source, 41)
    original_run = ParallelExecutor.run

    def replace_before_worker(self, **kwargs):
        producer(source, 99)
        return original_run(self, **kwargs)

    monkeypatch.setattr(ParallelExecutor, 'run', replace_before_worker)
    destination = tmp_path/'consumer'
    result = Project().submit(cfg(destination, source), isolated=True, smart_run=False)
    assert result.status == 'FAILED'
    assert 'changed or disappeared after submission' in result.error
    assert not (destination/'called').exists()
    assert not (destination/'run.complete').exists()
