"""Combined sweep transformation preserves public freeze/bind semantics."""
import pytest
from omegaconf import OmegaConf

from flexlock.freeze import freeze_deferred, _freeze_and_bind
from flexlock.resolvers import bind_existing_run_locks, resolve_deferred
from flexlock.run_record import RunRecord


@pytest.mark.parametrize('case', ['plain', 'container_alias', 'producer', 'future', 'default', 'latest'])
@pytest.mark.parametrize('readonly', [False, True])
def test_combined_freeze_binding_preserves_values_and_caller(tmp_path, case, readonly):
    producer = tmp_path/'producers'/'first'
    producer.mkdir(parents=True)
    RunRecord(producer).write_lock(dict(config=dict(value=['literal ${missing}', {'n': 3}]), timestamp='fixed'))
    path = str(producer)
    value = '${.item}'
    if case == 'container_alias':
        value = '${options}'
    elif case == 'producer':
        value = '${run_lock:${upstream},config.value}'
    elif case == 'future':
        path = str(tmp_path/'future')
        value = '${run_lock:${upstream},config.value}'
    elif case == 'default':
        path = str(tmp_path/'absent')
        value = '${run_lock:${upstream},config.value,null}'
    elif case == 'latest':
        path = '${latest:'+str(producer.parent/'*')+'}'
        value = '${run_lock:${upstream},config.value}'
    cfg = OmegaConf.create(dict(item=7, upstream=path, value=value,
                               options=dict(n='${item}', text='ordinary text')))
    OmegaConf.set_struct(cfg, True)
    OmegaConf.set_readonly(cfg, readonly)
    before = OmegaConf.to_container(cfg, resolve=False)
    expected = bind_existing_run_locks(freeze_deferred(cfg, defer_runs=True), allow_future=True)
    actual = _freeze_and_bind(cfg, allow_future=True)
    assert OmegaConf.to_container(actual, resolve=False) == OmegaConf.to_container(expected, resolve=False)
    assert OmegaConf.to_container(cfg, resolve=False) == before
    assert OmegaConf.is_readonly(cfg) == readonly
    if case != 'future':
        assert OmegaConf.to_container(resolve_deferred(actual), resolve=True) == OmegaConf.to_container(resolve_deferred(expected), resolve=True)
    else:
        assert str(tmp_path/'future') in OmegaConf.to_container(actual, resolve=False)['value']


def test_resolver_returned_producer_read_still_binds_after_freeze(tmp_path):
    source = tmp_path/'producer'
    source.mkdir()
    RunRecord(source).write_lock(dict(config=dict(value=41), timestamp='fixed'))
    # The live producer call exists only in a custom resolver's returned string.
    OmegaConf.register_new_resolver('hidden_producer', lambda: '${run_lock:'+str(source)+',config.value}')
    try:
        cfg = OmegaConf.create(dict(value='${hidden_producer:}'))
        actual = _freeze_and_bind(cfg)
        assert actual.value == 41
        assert actual._snapshot_.run_lock_reads[0].binding == 'submit'
        RunRecord(source).write_lock(dict(config=dict(value=99), timestamp='replaced'))
        from flexlock.exceptions import FlexLockValidationError
        with pytest.raises(FlexLockValidationError, match='changed or disappeared'):
            resolve_deferred(actual)
    finally:
        OmegaConf.clear_resolver('hidden_producer')


def test_plain_frozen_config_avoids_binding_pass(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('no interpolation remains to evaluate')
    monkeypatch.setattr('flexlock.resolvers._bind_detached_run_locks', unexpected)
    cfg = OmegaConf.create(dict(item=4, values=['${item}', dict(path='${item}/input')]))
    assert OmegaConf.to_container(_freeze_and_bind(cfg), resolve=False) == dict(item=4, values=[4, dict(path='4/input')])
    assert OmegaConf.to_container(cfg, resolve=False)['values'][0] == '${item}'
