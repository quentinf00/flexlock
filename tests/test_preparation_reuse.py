"""Effective config reuse preserves partial overrides and pre-queue guards."""
import json
import pytest
from omegaconf import OmegaConf

from flexlock.exceptions import FlexLockValidationError
from flexlock.parallel import ParallelExecutor
from flexlock.taskdb import get_all_tasks, queue_tasks, finish_task


def plain(value):
    return OmegaConf.to_container(value, resolve=False) if OmegaConf.is_config(value) else value


@pytest.mark.parametrize('target', [None, '.', 'payload'])
def test_partial_overrides_keep_master_output_contracts_and_queue_payloads(tmp_path, target):
    product = tmp_path/'products'
    item = '${payload.item}' if target == 'payload' else '${item}'
    cfg = OmegaConf.create(dict(save_dir=str(product), item=0, payload=dict(item=0),
        _outputs_=dict(part=dict(path='${save_dir}/part_'+item+'.json'))))
    tasks = [dict(item=1), dict(item=2)]
    before = plain(cfg)
    executor = ParallelExecutor(func=lambda cfg: None, cfg=cfg, tasks=tasks,
                                task_target=target)
    assert executor.shared_save_dirs == [str(product.resolve())]
    # Layout 2 discovers nested queues through their ancestor, without a pointer.
    assert not (product/'.flexlock-queue.json').exists()
    from flexlock.destination_guard import has_active_destination
    assert has_active_destination(product)
    rows = get_all_tasks(executor.db_path)
    assert sorted(plain(row['task'])['item'] for row in rows) == [1, 2]
    assert all(set(plain(row['task'])) == {'item'} and row['status'] == 'pending' for row in rows)
    assert plain(cfg) == before and tasks == [dict(item=1), dict(item=2)]


def test_shared_composite_contracts_resolve_against_each_stage_root(tmp_path):
    product = tmp_path/'products'
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path/'queue'), prefix='wrapper'))
    tasks = [dict(_stages_=[dict(save_dir=str(product), prefix=prefix,
        _outputs_=dict(part=dict(path='${prefix}.json')))]) for prefix in ['alpha', 'beta']]
    # If a stage remains attached to the wrapper, both output contracts resolve
    # to wrapper.json and incorrectly collide. Stage-root contracts are disjoint.
    executor = ParallelExecutor(func=lambda cfg: None, cfg=cfg, tasks=tasks, task_target=None)
    assert executor.shared_save_dirs == [str(product.resolve())]
    assert len(get_all_tasks(executor.db_path)) == 2
    assert cfg.prefix == 'wrapper'
    assert tasks[0]['_stages_'][0]['_outputs_']['part']['path'] == '${prefix}.json'


def test_completed_rows_still_participate_in_append_collision_checks(tmp_path):
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path), _outputs_=dict(part='same.json')))
    db = tmp_path/'run.lock.tasks.db'
    old = dict(item=1)
    queue_tasks(db, [old], tag='old')
    finish_task(db, old, result={})
    with pytest.raises(FlexLockValidationError, match='overlapping output'):
        ParallelExecutor(func=lambda cfg: None, cfg=cfg, tasks=[dict(item=2)],
                         task_target=None, tag='new')
    rows = get_all_tasks(db)
    assert len(rows) == 1 and rows[0]['status'] == 'done'
    assert plain(rows[0]['task']) == old
