"""Project discovery and item identity under serial/parallel shared product roots."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
from omegaconf import OmegaConf

from flexlock import Project
from flexlock.exceptions import FlexLockValidationError
from flexlock.record import list_task_records, load_record, load_task_record
from flexlock.registry import diagnose, initialize
from flexlock.run_record import RunRecord
from flexlock.outputs import validate_outputs


def produce(save_dir, item, fail=False):
    if fail:
        raise RuntimeError(f'injected item failure: {item}')
    p = Path(save_dir)/f'chunk_{item}.json'
    p.write_text(json.dumps({'item': item}))
    return {'item': item}


def config(root):
    return OmegaConf.create(dict(
        _target_='tests.test_registry_items.produce', save_dir=str(root/'products'),
        item=0, fail=False, _snapshot_=dict(repos={}),
        _outputs_=dict(chunk=dict(path='chunk_${item}.json', sha256=True)),
    ))


@pytest.fixture(autouse=True)
def selected_source(monkeypatch):
    monkeypatch.delenv('FLEXLOCK_INDEX', raising=False)
    monkeypatch.setenv('FLEXLOCK_INDEX_FALLBACK', '0')
    monkeypatch.setenv('PYTHONPATH', str(Path(__file__).parents[1]))
    monkeypatch.setattr('flexlock.worker.time.sleep', lambda _: None)


def test_init_idempotent_and_does_not_migrate_nested_indexes(tmp_path):
    nested = tmp_path/'outputs/deep/.flexlock'
    nested.mkdir(parents=True)
    old = nested/'index.db'; old.write_bytes(b'legacy sentinel')
    first = initialize(tmp_path)
    identity = (tmp_path/'.flexlock/project.json').read_bytes()
    second = initialize(tmp_path)
    assert first['project'] == second['project']
    assert identity == (tmp_path/'.flexlock/project.json').read_bytes()
    assert old.read_bytes() == b'legacy sentinel'
    info = diagnose(tmp_path/'other/nested/run')
    assert info['index_path'] == str(tmp_path/'.flexlock/index.db')


def test_doctor_no_writes_and_reports_actual_fallback(tmp_path):
    before = list(tmp_path.iterdir())
    info = diagnose(tmp_path/'missing')
    assert info['index_path'] == str(tmp_path/'missing/.flexlock/index.db')
    assert str(tmp_path/'missing/.flexlock/presets') in info['presets_roots']
    assert list(tmp_path.iterdir()) == before


def test_init_rejects_conflicting_override_before_writes(tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'external.db'))
    with pytest.raises(ValueError, match='FLEXLOCK_INDEX selects'):
        initialize(tmp_path)
    assert not (tmp_path/'.flexlock').exists()


def test_registry_cli_and_missing_preset_diagnostics(tmp_path):
    from flexlock.presets import resolve_run
    from flexlock.exceptions import FlexLockConfigError
    for command in ['init', 'doctor']:
        output = subprocess.check_output([sys.executable, '-m', 'flexlock.cli', command,
                                          str(tmp_path), '--format', 'json'], text=True)
        assert json.loads(output)['index_path'] == str(tmp_path/'.flexlock/index.db')
    import os
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        with pytest.raises(FlexLockConfigError, match=str(tmp_path/'.flexlock/presets')):
            resolve_run('missing.preset')
    finally:
        os.chdir(previous)


@pytest.mark.parametrize('n_jobs', [1, 2])
@pytest.mark.parametrize('mode', ['dir', 'db'])
def test_shared_items_independent_receipts_payloads_cache_and_reuse(tmp_path, n_jobs, mode):
    initialize(tmp_path)
    cfg = config(tmp_path)
    results = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], n_jobs=n_jobs,
                               task_record=mode)
    assert [r.status for r in results] == ['SUCCESS', 'SUCCESS']
    assert [r.get('item') for r in results] == [1, 2]
    assert len({r.record_dir for r in results}) == 2
    assert not (tmp_path/'products/run.complete').exists()
    db = Path(results[0].task_db)
    entries = list_task_records(db, check_outputs=True)
    assert len(entries) == 2
    assert all(e['status'] == 'done' and e['artifact_health'] == 'valid' for e in entries)
    for item, result in zip([1, 2], results):
        snapshot = load_record(result.record_dir)
        assert snapshot['config']['item'] == item
        assert snapshot['config']['save_dir'] == str(tmp_path/'products')
        assert load_task_record(db, result.task_id)['result'] == {'item': item}
        proposed = cfg.copy(); proposed.item = item
        cached = Project()._load_selected_result(Path(result.record_dir), proposed)
        assert cached.get('item') == item and cached.record_dir == result.record_dir
        assert cached.save_dir == str(tmp_path/'products')
    before = [(Path(r.record_dir)/'run.complete').stat().st_mtime_ns for r in results]
    again = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], n_jobs=n_jobs,
                             task_record=mode)
    assert [r.get('item') for r in again] == [1, 2]
    assert before == [(Path(r.record_dir)/'run.complete').stat().st_mtime_ns for r in again]
    raw_db = db.read_bytes()
    output = subprocess.check_output([sys.executable, '-m', 'flexlock.cli', 'items',
                                      str(db), '--check-outputs'], text=True)
    assert len(json.loads(output)) == 2 and db.read_bytes() == raw_db
    (tmp_path/'products/chunk_1.json').write_text('{}')
    health = list_task_records(db, check_outputs=True)
    assert sorted(e['artifact_health'] for e in health) == ['invalid', 'valid']
    assert all(e['status'] == 'done' for e in health)
    proposed = cfg.copy(); proposed.item = 1
    with pytest.raises(FlexLockValidationError, match='SHA256 differs'):
        Project()._load_selected_result(Path(results[0].record_dir), proposed)
    with pytest.raises(FlexLockValidationError, match='SHA256 differs'):
        Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], n_jobs=n_jobs,
                         task_record=mode)


@pytest.mark.parametrize('n_jobs', [1, 2])
def test_failure_keeps_other_shared_item_receipt_complete(tmp_path, n_jobs):
    results = Project().submit(config(tmp_path), sweep=[{'item': 1, 'fail': True}, {'item': 2}],
                               n_jobs=n_jobs)
    assert [r.status for r in results] == ['FAILED', 'SUCCESS']
    assert results[1].get('item') == 2
    assert (Path(results[1].record_dir)/'run.complete').is_file()
    assert (Path(results[0].record_dir)/'run.error').is_file()
    assert not (Path(results[0].record_dir)/'run.complete').exists()


def test_shared_declared_output_collision_rejected_before_execution(tmp_path):
    cfg = config(tmp_path); cfg._outputs_.chunk.path = 'same.json'
    with pytest.raises(FlexLockValidationError, match='overlapping output'):
        Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}])
    # Pre-submit guards can create a mutex directory; no work or queue may land.
    assert not (tmp_path/'products/same.json').exists()
    assert not list((tmp_path/'products').glob('chunk_*.json'))
    assert not (tmp_path/'products/run.complete').exists()
    assert not list(tmp_path.rglob('run.lock.tasks.db'))


def test_missing_task_database_is_not_created(tmp_path):
    p = tmp_path/'missing/tasks.db'
    with pytest.raises(Exception):
        list_task_records(p)
    assert not p.parent.exists()


def test_append_only_campaign_retains_shared_receipt_scope(tmp_path):
    initialize(tmp_path)
    cfg = config(tmp_path)
    first = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}])
    before = [(Path(r.record_dir)/'run.complete').read_bytes() for r in first]
    extended = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}, {'item': 3}],
                                )
    assert [r.status for r in extended] == ['SUCCESS', 'SUCCESS', 'SUCCESS']
    assert before == [(Path(r.record_dir)/'run.complete').read_bytes() for r in first]
    assert len({r.record_dir for r in extended}) == 3
    assert all(r.record_dir != r.save_dir for r in extended)
    assert len(list_task_records(extended[-1].task_db)) == 3
    assert not (tmp_path/'products/run.complete').exists()


@pytest.mark.parametrize('n_jobs', [1, 2])
def test_one_item_sweep_keeps_database_and_explicit_record_mode(tmp_path, n_jobs):
    cfg = config(tmp_path)
    result = Project().submit(cfg, sweep=[{'item': 1}], n_jobs=n_jobs, task_record='db')[0]
    assert result.status == 'SUCCESS' and result.task_id and result.task_db
    assert Path(result.task_db).is_file()
    assert load_record(result.record_dir)['config']['item'] == 1
    assert list_task_records(result.task_db)[0]['task_record'] == 'db'


def test_appending_campaign_does_not_rewrite_prior_item_note(tmp_path):
    cfg = config(tmp_path)
    first = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], task_record='db',
                              note='first campaign')
    Project().submit(cfg, sweep=[{'item': 3}], task_record='db',
                     note='appended campaign')
    assert all(load_record(r.record_dir)['note'] == 'first campaign' for r in first)


def test_absent_prior_note_does_not_inherit_appended_note_or_mode(tmp_path):
    cfg = config(tmp_path)
    first = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], task_record='db')
    Project().submit(cfg, sweep=[{'item': 3}], task_record='dir',
                     note='appended campaign')
    for result in first:
        assert load_record(result.record_dir).get('note') is None
        assert load_task_record(result.task_db, result.task_id)['task_record'] == 'db'


def test_nested_shared_receipts_do_not_claim_a_new_project_index(tmp_path):
    from flexlock.index import resolve_index_path
    initialize(tmp_path)
    cfg = config(tmp_path)
    results = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], task_record='db',
                               sweep_root=str(tmp_path/'campaign'))
    for result in results:
        assert resolve_index_path(Path(result.record_dir).parent) == tmp_path/'.flexlock/index.db'
        proposed = cfg.copy(); proposed.item = result.get('item')
        cached = Project()._load_selected_result(Path(result.record_dir), proposed)
        assert cached.task_id == result.task_id


@pytest.mark.parametrize('mode', ['dir', 'db'])
def test_shared_pipeline_records_are_readable_per_stage(tmp_path, mode):
    cfg = config(tmp_path)
    items = []
    for item in [1, 2]:
        stage = cfg.copy(); stage.item = item
        second = cfg.copy(); second.item = item + 10
        second.save_dir = str(tmp_path/'second-products')
        items.append([stage, second])
    results = Project().submit_pipeline(items, n_jobs=1, sweep_root=str(tmp_path),
                                        task_record=mode)
    assert len(results) == 2
    for item, stages in zip([1, 2], results):
        assert [s.status for s in stages] == ['SUCCESS', 'SUCCESS']
        assert [s.get('item') for s in stages] == [item, item+10]
        for stage in stages:
            assert load_record(stage.record_dir)['config']['item'] == stage.get('item')
