"""Corrective acceptance for the three independent-review reproductions."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from omegaconf import OmegaConf
from flexlock import Project
from flexlock.exceptions import FlexLockValidationError
from flexlock.record import list_task_records
from flexlock.taskdb import queue_tasks
from tests.test_registry_items import config


@pytest.mark.parametrize('route', ['pipeline', 'queue'])
def test_same_item_stage_alias_rejected_before_dispatch(tmp_path, monkeypatch, route):
    a = config(tmp_path); a.item = 1
    b = config(tmp_path); b.item = 2
    # Different spellings of the same concrete root must also be rejected.
    b.save_dir = str(tmp_path/'products/../products')
    backend = MagicMock(); monkeypatch.setattr('flexlock.parallel.SlurmBackend', backend)
    profile = tmp_path/'slurm.yaml';profile.write_text('startup_lines: []\n')
    with pytest.raises(FlexLockValidationError, match='distinct.*save_dir'):
        if route == 'pipeline':
            Project().submit_pipeline([[a, b]], slurm_config=str(profile), wait=False)
        else:
            from flexlock.parallel import ParallelExecutor
            from flexlock.utils import instantiate
            ParallelExecutor(func=instantiate, task_target=None,
                tasks=[{'_stages_': [OmegaConf.to_container(a), OmegaConf.to_container(b)]}],
                cfg=OmegaConf.create(dict(save_dir=str(tmp_path/'campaign'))),
                slurm_config=str(profile))
    backend.assert_not_called()
    assert not (tmp_path/'products').exists()
    assert not list(tmp_path.rglob('run.lock.tasks.db'))


def test_identical_completed_items_keep_results_across_tags(tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'.flexlock/index.db'))
    cfg = config(tmp_path)
    first = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], tag='first', smart_run=False)
    before = [(Path(r.record_dir)/'run.complete').read_bytes() for r in first]
    second = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], tag='second', smart_run=False)
    assert [r.status for r in second] == ['SUCCESS', 'SUCCESS']
    assert [r.get('item') for r in second] == [1, 2]
    assert [r.task_id for r in second] == [r.task_id for r in first]
    assert before == [(Path(r.record_dir)/'run.complete').read_bytes() for r in second]
    # Dedup membership is independent from a cosmetic new tag. Validate old outputs.
    (tmp_path/'products/chunk_1.json').write_text('{}')
    with pytest.raises(FlexLockValidationError, match='SHA256 differs'):
        Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], tag='third', smart_run=False)


def test_composite_completed_item_results_across_tags(tmp_path):
    a = config(tmp_path);a.item = 1
    b = config(tmp_path);b.item = 2;b.save_dir = str(tmp_path/'second')
    c = a.copy();c.item = 3
    d = b.copy();d.item = 4
    items = [[a, b], [c, d]]
    first = Project().submit_pipeline(items, sweep_root=str(tmp_path/'campaign'), tag='first')
    second = Project().submit_pipeline(items, sweep_root=str(tmp_path/'campaign'), tag='second')
    assert [[r.get('item') for r in stage] for stage in second] == [[1, 2], [3, 4]]
    assert all(r.status == 'SUCCESS' for stage in second for r in stage)
    assert [[r.record_dir for r in stage] for stage in second] == [[r.record_dir for r in stage] for stage in first]


@pytest.mark.parametrize('status', ['pending', 'running'])
def test_cross_tag_live_item_rejected_without_partial_queue_write(tmp_path, status):
    db = tmp_path/'tasks.db';task = dict(item=1)
    queue_tasks(db, [task], tag='owner')
    if status == 'running':
        from flexlock.taskdb import claim_next_task
        claim_next_task(db, 'node', tags=['owner'])
    with pytest.raises(FlexLockValidationError, match='another tag'):
        queue_tasks(db, [dict(item=2), task], tag='other')
    rows = list_task_records(db)
    assert len(rows) == 1 and rows[0]['tag'] == 'owner' and rows[0]['status'] == status


def test_missing_authoritative_database_rejects_cache_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'.flexlock/index.db'))
    monkeypatch.setenv('FLEXLOCK_INDEX_FALLBACK', '0')
    cfg = config(tmp_path);del cfg['_outputs_']
    result = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], task_record='db', smart_run=False)[0]
    assert result.record_dir != result.save_dir
    db = Path(result.task_db);db.unlink()
    proposed = cfg.copy();proposed.item = 1
    with pytest.raises(FlexLockValidationError, match='readable.*record'):
        Project()._load_cached_result(Path(result.record_dir), proposed)
    with pytest.raises(ValueError, match='No matching run'):
        Project().get_result(proposed, search_dirs=[str(tmp_path)])
    assert not db.exists()


@pytest.mark.parametrize('status', ['failed', 'interrupted'])
def test_executor_does_not_hide_prior_terminal_failure_under_other_tag(tmp_path, status):
    from flexlock.parallel import ParallelExecutor
    from flexlock.taskdb import finish_task
    task = dict(item=1)
    db = tmp_path/'run.lock.tasks.db'
    queue_tasks(db, [task], tag='original')
    finish_task(db, task, error='retained failure', status=status)
    fn = MagicMock()
    executor = ParallelExecutor(func=fn, tasks=[task], task_target=None,
                               cfg=OmegaConf.create(dict(save_dir=str(tmp_path))), tag='requested')
    assert executor.run() is False
    fn.assert_not_called()
    assert list_task_records(db)[0]['status'] == status
