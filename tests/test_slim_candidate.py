"""Boundaries replacing retired automatic cache and partial-resume policies."""
from pathlib import Path
from unittest.mock import Mock

import pytest
from omegaconf import OmegaConf

from flexlock import Project
from flexlock.exceptions import FlexLockValidationError
from tests.test_registry_items import config


@pytest.mark.parametrize('kwargs', [
    {'smart_run': True}, {'smart_run': False}, {'search_dirs': []},
    {'match_include': ['src']}, {'match_exclude': ['tests']},
])
@pytest.mark.parametrize('route', ['single', 'sweep', 'pipeline', 'stage'])
def test_retired_keywords_reject_without_dispatch(tmp_path, monkeypatch, kwargs, route):
    scheduler = Mock()
    monkeypatch.setattr('flexlock.parallel.SlurmBackend', scheduler)
    cfg = config(tmp_path)
    proj = Project()
    with pytest.raises(TypeError, match='unexpected keyword'):
        if route == 'pipeline':
            proj.submit_pipeline([[cfg]], **kwargs)
        elif route == 'stage':
            proj.run_stage(cfg, **kwargs)
        else:
            proj.submit(cfg, sweep=[{'item': 1}] if route == 'sweep' else None, **kwargs)
    scheduler.assert_not_called()
    assert not list(tmp_path.rglob('run.lock*'))
    assert not (tmp_path/'products').exists()


def test_fresh_destination_is_not_redirected_to_sibling(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('ordinary execution must not publish a cache index')
    monkeypatch.setattr('flexlock.index.record_run_lock', forbidden)
    monkeypatch.setattr('flexlock.index.record_task', forbidden)
    first = Project().submit(config(tmp_path/'first'))
    cfg = config(tmp_path/'second')
    second = Project().run_stage(cfg)
    assert first.status == second.status == 'SUCCESS'
    assert cfg.save_dir == second.save_dir == str(tmp_path/'second/products')
    assert first.save_dir != second.save_dir
    with pytest.raises(FlexLockValidationError, match='already contains'):
        Project().submit(cfg)


def test_explicit_reuse_preserves_recorded_config_and_output_contract(tmp_path):
    cfg = config(tmp_path)
    cfg.item = 1
    Project().submit(cfg)
    proposed = cfg.copy()
    proposed.item = 99
    del proposed['_outputs_']
    selected = Project().submit(proposed, save_dir_policy='skip')
    assert selected.status == 'CACHED'
    assert selected.cfg.item == selected.result['item'] == 1
    (Path(cfg.save_dir)/'chunk_1.json').write_text('corrupted')
    with pytest.raises(FlexLockValidationError, match='SHA256 differs'):
        Project().submit(proposed, save_dir_policy='skip')


def test_partial_pipeline_is_not_resumed_from_markers(tmp_path):
    first = config(tmp_path/'first')
    second = config(tmp_path/'second')
    Project().submit(first)
    marker = (Path(first.save_dir)/'run.complete').read_bytes()
    with pytest.raises(FlexLockValidationError, match='partially complete pipeline'):
        Project().submit_pipeline([[first, second]], save_dir_policy='skip',
                                  sweep_root=str(tmp_path/'campaign'))
    assert (Path(first.save_dir)/'run.complete').read_bytes() == marker
    assert not (tmp_path/'campaign/run.lock.tasks.db').exists()
    assert not (Path(second.save_dir)/'run.lock').exists()
    assert not (Path(second.save_dir)/'chunk_0.json').exists()
    Project().submit(second)
    selected = Project().submit_pipeline([[first, second]], save_dir_policy='skip',
                                         sweep_root=str(tmp_path/'campaign'))
    assert [r.status for r in selected[0]] == ['CACHED', 'CACHED']


def test_old_resume_payload_rejected_before_queue_creation(tmp_path):
    from flexlock.parallel import ParallelExecutor
    from flexlock.utils import instantiate
    cfg = config(tmp_path)
    with pytest.raises(FlexLockValidationError, match='Marker-based stage resume is retired'):
        ParallelExecutor(func=instantiate, tasks=[{'_stages_': [dict(cfg)],
                         '_skip_complete_': True}], task_target=None,
                         cfg=OmegaConf.create({'save_dir': str(tmp_path/'campaign')}))
    assert not list(tmp_path.rglob('run.lock*'))


def test_retired_search_and_fanout_methods_are_absent():
    import flexlock.api as api
    for name in ('exists', 'get_result', 'submit_chained', '_find_matching_run',
                 '_glob_scan_match', '_generate_fingerprint'):
        assert not hasattr(Project, name)
    assert not hasattr(api, 'ChainedResult')


def test_unchanged_queue_drains_pending_without_reexecuting_done(tmp_path, monkeypatch):
    from flexlock.parallel import ParallelExecutor
    from flexlock.taskdb import claim_next_task, finish_tasks, get_all_tasks
    from flexlock.utils import instantiate
    from flexlock.worker import _run_one_task

    monkeypatch.setattr('flexlock.worker.time.sleep', lambda _: None)
    tasks = [OmegaConf.to_container(config(tmp_path/str(i))) for i in range(2)]
    base = OmegaConf.create(dict(save_dir=str(tmp_path/'campaign'), _snapshot_=dict(repos={})))
    executor = ParallelExecutor(instantiate, tasks, None, base, n_jobs=1)
    first = claim_next_task(executor.db_path, 'initial-worker', tags=[executor.tag])
    finished = []
    _run_one_task(instantiate, base, None, executor.db_path, executor.save_dir,
                  executor.save_dir/'run.lock', 'initial-worker', first, finished)
    finish_tasks(executor.db_path, finished)
    assert sorted(row['status'] for row in get_all_tasks(executor.db_path)) == ['done', 'pending']
    marker = Path(first['save_dir'])/'run.complete'
    before = marker.read_bytes()
    assert executor.run()
    assert [row['status'] for row in get_all_tasks(executor.db_path)] == ['done', 'done']
    assert marker.read_bytes() == before


@pytest.mark.parametrize('route', ['serial', 'parallel', 'pipeline'])
def test_public_queue_continuation_accepts_only_same_recorded_payload(tmp_path, monkeypatch, route):
    monkeypatch.setattr('flexlock.worker.time.sleep', lambda _: None)
    cfg = config(tmp_path/'item')
    other = config(tmp_path/'other')
    queue = tmp_path/'queue'
    def submit(root, selected):
        if route == 'pipeline':
            return Project().submit_pipeline([[selected, other]], sweep_root=str(root))
        return Project().submit(selected, sweep=[{}], sweep_root=str(root),
                                n_jobs=2 if route == 'parallel' else 1)
    submit(queue, cfg)
    marker = Path(cfg.save_dir)/'run.complete'
    before = marker.read_bytes()
    submit(queue, cfg)
    assert marker.read_bytes() == before
    changed = cfg.copy();changed.item = 77
    with pytest.raises(FlexLockValidationError, match='already contains'):
        submit(queue, changed)
    with pytest.raises(FlexLockValidationError, match='already contains'):
        submit(tmp_path/'foreign-queue', cfg)
    assert marker.read_bytes() == before
