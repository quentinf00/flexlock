"""Experimental, bounded process compilation; ordinary submission stays serial.

FLEXLOCK_PREP_PROCESSES opts a guarded Python entry point into this experiment.
Only canonical configs with ordinary references and the stock run_lock resolver
are eligible. Unsupported contexts retain the existing controller-side path.
"""
import inspect
import multiprocessing
import os
import pickle
import re
from concurrent.futures import ProcessPoolExecutor

from omegaconf import DictConfig, ListConfig, OmegaConf

_MIN_ITEMS = 512
_BATCH_SIZE = 50
_BASE = None
_TARGET = None
_AFTER = False


def _compile_item(base, override, target, after):
    from .utils import merge_task_into_cfg
    from .presets import freeze_run_refs, validate_chained_paths
    from .freeze import _freeze_and_bind

    cfg = merge_task_into_cfg(base, override, target)
    freeze_run_refs(cfg, defer_unpinned=after)
    if after:
        validate_chained_paths(cfg)
    return _freeze_and_bind(cfg, allow_future=after)


def _canonical(value):
    if isinstance(value, (DictConfig, ListConfig)):
        if OmegaConf.get_type(value) not in (dict, list) or OmegaConf.get_cache(value):
            return False
        keys = value.keys() if isinstance(value, DictConfig) else range(len(value))
        if not all(_canonical(value._get_node(k)) for k in keys
                   if isinstance(value._get_node(k), (DictConfig, ListConfig))):
            return False
        value = OmegaConf.to_container(value, resolve=False)
    if isinstance(value, dict):
        return all(type(k) is str and _canonical(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return all(_canonical(v) for v in value)
    if isinstance(value, str):
        if '${' in value and ':' in value:
            names = re.findall(r'\$\{([^{}:$]*):', value)
            return bool(names) and all(name == 'run_lock' for name in names)
        return True
    return value is None or type(value) in (bool, int, float)


def _workers(base, sweep):
    requested = int(os.environ.get('FLEXLOCK_PREP_PROCESSES', '1'))
    if requested <= 1 or len(sweep) < _MIN_ITEMS:
        return 1
    # Never create a nested preparation pool in a spawned child.
    if multiprocessing.current_process().name != 'MainProcess':
        return 1
    available = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else (os.cpu_count() or 1)
    allocation = int(os.environ.get('SLURM_CPUS_PER_TASK', str(available)))
    workers = min(requested, available, allocation, 4)
    if workers <= 1 or base._get_parent() is not None or not _canonical(base) or not _canonical(sweep):
        return 1
    # A same-name replacement must not silently change behavior under spawn.
    from .resolvers import run_lock_resolver
    wrapper = OmegaConf._get_resolver('run_lock')
    if wrapper is None or inspect.getclosurevars(wrapper).nonlocals.get('resolver') is not run_lock_resolver:
        return 1
    try:
        pickle.dumps((base, sweep))
    except (TypeError, pickle.PicklingError, AttributeError):
        return 1
    return workers


def _initialize(base, target, after):
    global _BASE, _TARGET, _AFTER
    _BASE, _TARGET, _AFTER = base, target, after


def _compile_batch(items):
    return [(i, _compile_item(_BASE, override, _TARGET, _AFTER)) for i, override in items]


def compile_sweep(base, sweep, target=None, *, after=False):
    """Return ordered detached OmegaConf configs, or propagate compilation errors.

    Pool failures deliberately do not retry: a producer may have changed since
    earlier bindings. The caller has not queued or dispatched anything yet.
    Pickled configs preserve metadata instead of recreating plain containers.
    """
    workers = _workers(base, sweep)
    if workers == 1:
        return [(i, _compile_item(base, override, target, after))
                for i, override in enumerate(sweep)]
    items = list(enumerate(sweep))
    batches = [items[i:i + _BATCH_SIZE] for i in range(0, len(items), _BATCH_SIZE)]
    with ProcessPoolExecutor(max_workers=workers,
                             mp_context=multiprocessing.get_context('spawn'),
                             initializer=_initialize, initargs=(base, target, after)) as pool:
        return [item for batch in pool.map(_compile_batch, batches) for item in batch]
