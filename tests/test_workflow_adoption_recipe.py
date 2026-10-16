"""Supported adoption recipe: explicit project index and one root per item."""
import json
from pathlib import Path

import pytest
from omegaconf import OmegaConf

from flexlock import Project
from flexlock.index import resolve_index_path
from flexlock.record import load_record


def produce(save_dir, item):
    Path(save_dir, 'product.json').write_text(json.dumps({'item': item}))
    return {'item': item}


@pytest.mark.parametrize('n_jobs', [1, 2])
@pytest.mark.parametrize('record_mode', ['dir', 'db'])
def test_explicit_registry_and_logical_items(tmp_path, monkeypatch, n_jobs, record_mode):
    monkeypatch.delenv('FLEXLOCK_INDEX', raising=False)
    monkeypatch.setenv('FLEXLOCK_INDEX_FALLBACK', '0')
    project = tmp_path/'project'
    # Explicitly claim the project before any output roots/index DB exist.
    (project/'.flexlock').mkdir(parents=True)
    cfg = OmegaConf.create(dict(
        _target_='tests.test_workflow_adoption_recipe.produce',
        save_dir=str(project/'products/base'), item=0,
        _snapshot_=dict(repos={}),
        _outputs_=dict(product=dict(path='product.json', sha256=True)),
    ))
    sweep = [dict(item=i, save_dir=str(project/f'products/item_{i}')) for i in [1, 2]]
    results = Project().submit(cfg, sweep=sweep, n_jobs=n_jobs, task_record=record_mode,
                                sweep_root=str(project/'campaign'))
    assert [r.status for r in results] == ['SUCCESS', 'SUCCESS']
    assert [r.get('item') for r in results] == [1, 2]
    for i in [1, 2]:
        record = load_record(project/f'products/item_{i}')
        assert record['config']['item'] == i
        assert record['fingerprint']
    sibling = project/'reassessment'
    sibling.mkdir()
    monkeypatch.chdir(sibling)
    assert resolve_index_path(sibling) == project/'.flexlock/index.db'
    for item in sweep:
        proposed = cfg.copy()
        proposed.item = item['item']
        proposed.save_dir = item['save_dir']
        cached = Project().submit(proposed, save_dir_policy='skip')
        assert cached.status == 'CACHED'
        assert cached.get('item') == item['item']
        assert cached.save_dir == item['save_dir']
