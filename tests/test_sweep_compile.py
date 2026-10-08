from dataclasses import dataclass

import pytest
from omegaconf import OmegaConf

from flexlock import sweep_compile as sc
from flexlock.run_record import RunRecord
from flexlock.resolvers import resolve_deferred
from flexlock.exceptions import FlexLockValidationError


@pytest.fixture
def processes(monkeypatch):
    monkeypatch.setenv('FLEXLOCK_PREP_PROCESSES', '2')
    monkeypatch.setenv('SLURM_CPUS_PER_TASK', '2')
    monkeypatch.setattr(sc, '_MIN_ITEMS', 2)
    monkeypatch.setattr(sc, '_BATCH_SIZE', 2)
    if hasattr(sc.os, 'sched_getaffinity') and len(sc.os.sched_getaffinity(0)) < 2:
        pytest.skip('requires two allocated CPUs')


@pytest.mark.parametrize('case', ['plain', 'producer', 'future', 'target'])
def test_spawned_configs_preserve_order_values_and_bindings(tmp_path, processes, monkeypatch, case):
    producer = tmp_path/'producer'
    RunRecord(producer).write_lock(dict(config=dict(value=['literal ${missing}', dict(n=41)]), timestamp='fixed'))
    base = OmegaConf.create(dict(item=0, save_dir=str(tmp_path/'${item}'), options=dict(n='${item}')))
    after = case == 'future'
    if case in ('producer', 'future'):
        base.upstream = str(tmp_path/'future') if after else str(producer)
        base.value = '${run_lock:${upstream},config.value}'
    target = None
    if case == 'target':
        base.save_dir = str(tmp_path/'${stage.item}')
        base.options.n = '${stage.item}'
        base = OmegaConf.create(dict(stage=base))
        target = 'stage'
    sweep = [dict(item=i) for i in range(6)]
    before = OmegaConf.to_container(base, resolve=False)
    assert sc._workers(base, sweep) == 2
    actual = sc.compile_sweep(base, sweep, target, after=after)
    monkeypatch.setenv('FLEXLOCK_PREP_PROCESSES', '1')
    expected = sc.compile_sweep(base, sweep, target, after=after)
    assert [(i, OmegaConf.to_container(cfg, resolve=False)) for i, cfg in actual] == [
        (i, OmegaConf.to_container(cfg, resolve=False)) for i, cfg in expected]
    assert OmegaConf.to_container(base, resolve=False) == before
    assert all(cfg._get_parent() is None for _, cfg in actual)
    if case == 'producer':
        RunRecord(producer).write_lock(dict(config=dict(value=99), timestamp='changed'))
        for _, cfg in actual:
            with pytest.raises(FlexLockValidationError, match='changed or disappeared'):
                resolve_deferred(cfg)


@dataclass
class Typed:
    item: int = 0


@pytest.mark.parametrize('case', ['small', 'custom', 'latest', 'run', 'typed', 'nested_typed', 'cache', 'attached', 'cpu', 'interactive'])
def test_unsupported_contexts_stay_serial(processes, monkeypatch, case):
    base = OmegaConf.create(dict(item=0))
    sweep = [dict(item=i) for i in range(6)]
    if case == 'small':
        sweep = sweep[:1]
    elif case in ('custom', 'latest', 'run'):
        base.value = '${'+case+':whatever}'
    elif case == 'typed':
        base = OmegaConf.structured(Typed)
    elif case == 'nested_typed':
        base.nested = OmegaConf.structured(Typed)
    elif case == 'cache':
        OmegaConf.set_cache(base, {'custom': {'args': 1}})
    elif case == 'attached':
        base = OmegaConf.create(dict(stage=base)).stage
    elif case == 'cpu':
        monkeypatch.setenv('SLURM_CPUS_PER_TASK', '1')
    elif case == 'interactive':
        monkeypatch.setattr(sc.sys.modules['__main__'], '__file__', '<stdin>')
    assert sc._workers(base, sweep) == 1


def test_parent_custom_resolver_runs_on_serial_fallback(processes):
    OmegaConf.register_new_resolver('local_only', lambda n: int(n)+7)
    try:
        cfg = OmegaConf.create(dict(item=0, value='${local_only:${item}}'))
        assert [c.value for _, c in sc.compile_sweep(cfg, [dict(item=i) for i in range(6)])] == list(range(7, 13))
    finally:
        OmegaConf.clear_resolver('local_only')


def test_replaced_run_lock_stays_serial(processes):
    from omegaconf.basecontainer import BaseContainer
    original = BaseContainer._resolvers['run_lock']
    OmegaConf.register_new_resolver('run_lock', lambda *args: 7, replace=True)
    try:
        cfg = OmegaConf.create(dict(value='${run_lock:somewhere,value}'))
        assert sc._workers(cfg, [dict(item=i) for i in range(6)]) == 1
    finally:
        BaseContainer._resolvers['run_lock'] = original


def test_pool_compilation_error_prevents_return(tmp_path, processes):
    from flexlock import Project
    cfg = OmegaConf.create(dict(item=0, value='${missing}'))
    with pytest.raises(Exception, match='missing'):
        Project()._submit_sweep(cfg, [dict(item=i) for i in range(6)], 2, False, [],
                                sweep_root=str(tmp_path/'queue'))
    assert not (tmp_path/'queue').exists()


def test_flags_match_serial_freeze_behavior(processes, monkeypatch):
    cfg = OmegaConf.create(dict(item=0, value='${item}'))
    OmegaConf.set_struct(cfg, True)
    OmegaConf.set_readonly(cfg, True)
    actual = sc.compile_sweep(cfg, [dict(item=i) for i in range(6)])
    monkeypatch.setenv('FLEXLOCK_PREP_PROCESSES', '1')
    expected = sc.compile_sweep(cfg, [dict(item=i) for i in range(6)])
    assert [(OmegaConf.is_struct(c), OmegaConf.is_readonly(c), c.value) for _, c in actual] == [
        (OmegaConf.is_struct(c), OmegaConf.is_readonly(c), c.value) for _, c in expected]
    assert OmegaConf.is_struct(cfg) and OmegaConf.is_readonly(cfg)
