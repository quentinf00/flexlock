"""Reuse frozen Project guard inputs without changing partial or historical tasks."""
import json

import pytest
from omegaconf import OmegaConf

from flexlock.parallel import ParallelExecutor
from flexlock.exceptions import FlexLockValidationError
from flexlock.taskdb import queue_tasks, finish_task, get_all_tasks


def trace_merges(monkeypatch):
    import flexlock.utils as utils
    calls = []
    original = utils.merge_task_into_cfg

    def traced(cfg, task, target):
        calls.append(OmegaConf.to_container(task, resolve=False) if OmegaConf.is_config(task) else task)
        return original(cfg, task, target)
    monkeypatch.setattr(utils, 'merge_task_into_cfg', traced)
    return calls


@pytest.mark.parametrize('compiled', [False, True])
def test_frozen_items_guard_and_payload_equivalence(tmp_path, monkeypatch, compiled):
    calls = trace_merges(monkeypatch)
    product = tmp_path/'products'
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path/'queue'), _snapshot_=dict(data=dict(controller='anything'))))
    tasks = [OmegaConf.create(dict(save_dir=str(product), item=i,
                                  _outputs_=dict(part=dict(path=f'part_{i}.json')))) for i in range(3)]
    before = [OmegaConf.to_container(t, resolve=False) for t in tasks]
    executor = ParallelExecutor(func=lambda c: None, cfg=cfg, tasks=tasks,
                                task_target=None, _compiled_tasks=compiled)
    assert len(calls) == (0 if compiled else 3)
    assert executor.shared_save_dirs == [str(product.resolve())]
    assert json.loads((product/'.flexlock-queue.json').read_text())['task_db'] == str(executor.db_path.resolve())
    rows = get_all_tasks(executor.db_path)
    assert sorted((r['task'] for r in rows), key=lambda t: t['item']) == before
    assert [OmegaConf.to_container(t, resolve=False) for t in tasks] == before
    # Controller provenance remains in the wrapper for the unchanged worker merge.
    assert cfg._snapshot_.data.controller == 'anything'


@pytest.mark.parametrize('compiled', [False, True])
def test_historical_partial_rows_still_guard_append(tmp_path, monkeypatch, compiled):
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path/'queue')))
    product = tmp_path/'products'
    old = dict(save_dir=str(product), _outputs_=dict(part='same.json'), item=0)
    db = tmp_path/'queue'/'run.lock.tasks.db'
    queue_tasks(db, [old], tag='old')
    finish_task(db, old, result={})
    task = OmegaConf.create(dict(save_dir=str(product), _outputs_=dict(part='same.json'), item=1))
    calls = trace_merges(monkeypatch)
    with pytest.raises(FlexLockValidationError, match='overlapping output'):
        ParallelExecutor(func=lambda c: None, cfg=cfg, tasks=[task], task_target=None,
                         _compiled_tasks=compiled, tag='new')
    assert old in calls
    assert len(get_all_tasks(db)) == 1


@pytest.mark.parametrize('case', ['missing_save', 'wrapper_defaults', 'partial_target', 'plain_dict'])
def test_incomplete_or_low_level_context_retains_merge(tmp_path, monkeypatch, case):
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path/'queue')))
    task = OmegaConf.create(dict(save_dir=str(tmp_path/'product'), item=1))
    target = None
    if case == 'missing_save':
        del task.save_dir
    elif case == 'wrapper_defaults':
        cfg._outputs_ = dict(part='inherited.json')
    elif case == 'partial_target':
        cfg.payload = dict(item=0)
        task = OmegaConf.create(dict(item=1))
        target = 'payload'
    elif case == 'plain_dict':
        task = OmegaConf.to_container(task, resolve=False)
    calls = trace_merges(monkeypatch)
    executor = ParallelExecutor(func=lambda c: None, cfg=cfg, tasks=[task], task_target=target,
                                _compiled_tasks=True)
    assert len(calls) == 1
    assert len(get_all_tasks(executor.db_path)) == 1


def test_project_passes_frozen_items_without_second_guard_merge(tmp_path, monkeypatch):
    from flexlock import Project
    calls = trace_merges(monkeypatch)
    monkeypatch.setattr(ParallelExecutor, 'run', lambda self, **kw: True)
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path/'queue'), item=0,
                               _target_='benchmarks.thousand_items.task.run_item',
                               _snapshot_=dict(discover=dict(repos=False, prevs=False))))
    Project()._submit_sweep(cfg, [dict(item=1), dict(item=2)], 1, False, [], dir_suffix=True)
    # One merge per item in the compiler, none in executor preparation.
    assert len(calls) == 2
    assert len(get_all_tasks(tmp_path/'queue'/'run.lock.tasks.db')) == 2
