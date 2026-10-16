"""Known references versus explicitly scoped heuristic discovery."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from omegaconf import OmegaConf
from flexlock.api import Project
from flexlock.resolvers import resolve_deferred
from flexlock.snapshot import snapshot
from flexlock.utils import extract_tracking_info


def make_record(directory, **values):
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'run.lock').write_text(yaml.safe_dump(dict(config=values)))
    return directory


def use(value, save_dir, second=None):
    return dict(value=value, second=second)


def test_direct_read_without_data_or_prevs_records_external_product(tmp_path):
    external = tmp_path/'outside/product';external.parent.mkdir();external.write_text('data')
    producer = make_record(tmp_path/'producer', output_path=str(external))
    cfg = dict(_target_='tests.test_discovery_policy.use', save_dir=str(tmp_path/'consumer'),
               value='${run_lock:'+str(producer)+',config.output_path}')
    result = Project().submit(cfg)
    record = yaml.safe_load((Path(result.save_dir)/'run.lock').read_text())
    assert record['config']['value'] == str(external)
    assert record['lineage']['producer']['path'] == str(producer)
    read = record['run_lock_reads'][0]
    assert read['field'] == 'config.output_path' and read['value'] == str(external)
    assert len(read['record_sha256']) == 64 and not read['used_default']
    assert {entry['method'] for entry in record['discovery']['lineage']} == {'run_lock'}


def test_same_producer_read_once_and_snapshot_does_not_substitute_changed_record(tmp_path):
    producer = make_record(tmp_path/'producer', value='old', other=2)
    alias = tmp_path/'alias';alias.symlink_to(producer, target_is_directory=True)
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path/'consumer'),
        value='${run_lock:'+str(producer)+',config.value}',
        second='${run_lock:'+str(alias)+',config.other}'))
    from flexlock.record import load_record
    with patch('flexlock.record.load_record', wraps=load_record) as loader:
        resolved = resolve_deferred(cfg)
        assert loader.call_count == 1
    make_record(producer, value='changed', other=99)
    captured = snapshot(resolved, prevs=[str(producer)], return_snapshot=True)
    assert captured['config']['value'] == 'old' and captured['config']['second'] == 2
    assert captured['lineage']['producer']['info']['config']['value'] == 'old'
    assert {entry['path'] for entry in captured['run_lock_reads']} == {str(producer)}


@pytest.mark.parametrize('existing', [False, True])
def test_explicit_default_is_recorded_without_inventing_missing_lineage(tmp_path, existing):
    producer = tmp_path/'producer'
    if existing:make_record(producer, unrelated=1)
    resolved = resolve_deferred(OmegaConf.create(dict(save_dir=str(tmp_path/'consumer'),
        value='${run_lock:'+str(producer)+',config.absent,null}')))
    record = snapshot(resolved, return_snapshot=True)
    assert record['run_lock_reads'][0]['used_default'] and record['config']['value'] is None
    assert bool(record.get('lineage')) == existing


def test_effective_data_argument_and_disabled_heuristic_keep_known_reference(tmp_path):
    first = make_record(tmp_path/'a', value=1)
    second = make_record(tmp_path/'b', value=2)
    input_file = first/'input';input_file.write_text('old')
    replacement = tmp_path/'replacement';replacement.write_text('new')
    cfg = OmegaConf.create(dict(input_path=str(input_file), save_dir=str(tmp_path/'consumer'),
        value='${run_lock:'+str(second)+',config.value}',
        _snapshot_=dict(discover=dict(prevs=False, repos=False), data=dict(dataset='${...input_path}'))))
    cfg.input_path = str(replacement)
    resolved = resolve_deferred(cfg)
    repos, data, prevs = extract_tracking_info(resolved)
    assert data == dict(dataset=str(replacement)) and repos == {} and prevs == []
    record = snapshot(resolved, data=data, prevs=prevs, return_snapshot=True)
    assert set(record['lineage']) == {'b'}
    assert all(entry['method'] == 'run_lock' for entry in record['discovery']['lineage'])


def test_ancestor_association_is_labelled_as_inferred(tmp_path):
    producer = make_record(tmp_path/'producer', arbitrary=True)
    data_file = producer/'unowned/input';data_file.parent.mkdir();data_file.write_text('data')
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path/'consumer'),
        _snapshot_=dict(data=dict(input=str(data_file)))))
    repos, data, prevs = extract_tracking_info(cfg)
    record = snapshot(cfg, repos=repos, data=data, prevs=prevs, return_snapshot=True)
    assert record['discovery']['lineage'] == [dict(method='data_ancestor', path=str(producer),
                                                  data='input', input_path=str(data_file))]


def test_explicit_canonical_checkout_suppresses_unfiltered_auto_alias(tmp_path):
    alias = tmp_path/'alias';alias.symlink_to(tmp_path, target_is_directory=True)
    cfg = OmegaConf.create(dict(_target_='pkg.stage.run',
        _snapshot_=dict(repos=dict(main=dict(path=str(alias), include=['src/'])))))
    with patch('flexlock.utils.resolve_module_to_repo_path', return_value=str(tmp_path)):
        repos, _, _ = extract_tracking_info(cfg)
    assert set(repos) == {'main'} and repos['main']['include'] == ['src/']


@pytest.mark.parametrize('discover', [dict(repos='yes'), dict(unknown=True), False])
def test_discovery_flags_are_explicit_booleans(discover):
    from flexlock.exceptions import FlexLockConfigError
    with pytest.raises(FlexLockConfigError, match='boolean'):
        extract_tracking_info(OmegaConf.create(dict(_snapshot_=dict(discover=discover))))


def test_same_named_known_producers_and_capture_scope_are_preserved(tmp_path):
    a = make_record(tmp_path/'a/prepare', value=1)
    b = make_record(tmp_path/'b/prepare', value=2)
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path/'consumer'),
        value='${run_lock:'+str(a)+',config.value}',
        second='${run_lock:'+str(b)+',config.value}'))
    first = snapshot(resolve_deferred(cfg), return_snapshot=True)
    assert set(first['lineage']) == {str(a), str(b)}
    assert 'run_lock_records' not in first['config']['_snapshot_']
    make_record(a, value=3)
    second = snapshot(resolve_deferred(cfg), return_snapshot=True)
    assert first['config']['value'] == 1 and second['config']['value'] == 3


@pytest.mark.parametrize('existing', [False, True])
def test_required_reference_fails_before_output_creation(tmp_path, existing):
    from omegaconf.errors import InterpolationResolutionError
    producer = tmp_path/'producer'
    if existing:make_record(producer, unrelated=1)
    consumer = tmp_path/'consumer'
    with pytest.raises(InterpolationResolutionError, match='not found|no run.lock found'):
        Project().submit(dict(_target_='tests.test_discovery_policy.use', save_dir=str(consumer),
            value='${run_lock:'+str(producer)+',config.required}'))
    assert not consumer.exists()


@pytest.mark.parametrize('mode', ['dir', 'db'])
def test_worker_records_known_reference_to_directory_or_database_producer(tmp_path, monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from flexlock.record import load_record
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'index.db'))
    monkeypatch.setattr('flexlock.worker.time.sleep', lambda _: None)
    producer = tmp_path/'producer'
    Project().submit(dict(_target_='tests.test_discovery_policy.use', save_dir=str(producer), value=41,
        _snapshot_=dict(discover=dict(repos=False))), sweep=[dict()],
         task_record=mode)
    assert load_record(producer)['config']['value'] == 41
    # Relative DB markers must resolve against the real producer, even when
    # the selected record is a symlink located in another directory.
    from flexlock.resolvers import run_lock_resolver
    alias = tmp_path/'aliases/selected';alias.parent.mkdir();alias.symlink_to(producer, target_is_directory=True)
    assert run_lock_resolver(str(alias), 'config.value') == 41
    backend = MagicMock();backend.submit.return_value = SimpleNamespace(job_id='88')
    monkeypatch.setattr('flexlock.parallel.SlurmBackend', lambda **kw: backend)
    profile = tmp_path/'slurm.yaml';profile.write_text('startup_lines: []\n')
    consumer = tmp_path/'consumer'
    result = Project().submit(dict(_target_='tests.test_discovery_policy.use', save_dir=str(consumer),
        value='${run_lock:'+str(producer)+',config.value}',
        _snapshot_=dict(discover=dict(repos=False, prevs=False))),
         slurm_config=str(profile), after=['77'], wait=False)
    assert result.status == 'SUBMITTED'
    args, kwargs = backend.submit.call_args
    args[0](*args[1:], **kwargs)
    record = load_record(consumer)
    assert record['config']['value'] == 41
    assert record['run_lock_reads'][0]['path'] == str(producer)
    assert record['lineage']['producer']['info']['config']['value'] == 41
    assert record['discovery']['lineage'][0]['method'] == 'run_lock'
