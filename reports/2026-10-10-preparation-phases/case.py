"""Lightweight nested phase accounting; no production instrumentation."""
from collections import defaultdict
from contextlib import contextmanager
from functools import wraps
import importlib
import json
from pathlib import Path
import runpy
import sys
import threading
import time
import os

# Cache paths are initialized during imports, before the measurement driver.
output = Path(sys.argv[sys.argv.index('--output')+1])
os.environ['FLEXLOCK_CACHE'] = str(output.with_name(output.name+'-hash-cache'))
os.environ['FLEXLOCK_INDEX'] = str(output/'index.db')

# Import caller aliases before patching so each original function has one wrapper.
modules = [importlib.import_module('flexlock.'+name) for name in
           ('api', 'parallel', 'taskdb', 'destination_guard', 'sweep_compile',
            'freeze', 'utils', 'record', 'snapshot', 'save_dir', 'resolvers')]
by_name = {m.__name__.split('.')[-1]: m for m in modules}
local = threading.local()
metrics = defaultdict(lambda: dict(calls=0, inclusive_wall=0., exclusive_wall=0.,
                                   inclusive_cpu=0., exclusive_cpu=0.))
lock = threading.Lock()


@contextmanager
def span(label):
    stack = getattr(local, 'stack', None)
    if stack is None:
        stack = local.stack = []
    frame = [0., 0.]
    stack.append(frame)
    wall, cpu = time.perf_counter(), time.thread_time()
    try:
        yield
    finally:
        wall, cpu = time.perf_counter()-wall, time.thread_time()-cpu
        stack.pop()
        if stack:
            stack[-1][0] += wall
            stack[-1][1] += cpu
        thread = 'main' if threading.current_thread() is threading.main_thread() else 'io_workers'
        with lock:
            entry = metrics[thread+':'+label]
            entry['calls'] += 1
            entry['inclusive_wall'] += wall
            entry['exclusive_wall'] += wall-frame[0]
            entry['inclusive_cpu'] += cpu
            entry['exclusive_cpu'] += cpu-frame[1]


def wrapped(original, label):
    @wraps(original)
    def call(*args, **kwargs):
        with span(label):
            return original(*args, **kwargs)
    return call


def patch_function(module, name, label):
    original = getattr(module, name)
    replacement = wrapped(original, label)
    for loaded in list(sys.modules.values()):
        if loaded and getattr(loaded, '__name__', '').startswith('flexlock'):
            for key, value in list(vars(loaded).items()):
                if value is original:
                    setattr(loaded, key, replacement)


for module, name, label in [
    ('sweep_compile', 'compile_sweep', 'compile'),
    ('utils', 'merge_task_into_cfg', 'config_merge'),
    ('freeze', '_freeze_and_bind', 'freeze_bind'),
    ('resolvers', '_bind_detached_run_locks', 'producer_binding'),
    ('taskdb', '_hash_task', 'task_hash'),
    ('taskdb', '_to_yaml', 'queue_yaml'),
    ('taskdb', '_write_txn', 'sqlite_write_transaction'),
    ('taskdb', 'queue_tasks', 'queue_insert'),
    ('parallel', '_default_tag', 'campaign_tag'),
    ('parallel', '_shared_product_roots_from_items', 'shared_roots'),
    ('utils', 'collect_task_repos', 'task_repo_collection'),
    ('snapshot', 'snapshot', 'master_snapshot'),
    ('record', '_list_task_records', 'record_selection'),
    ('destination_guard', '_map_io', 'metadata_pool'),
    ('destination_guard', '_write_reservation', 'reservation_file'),
    ('destination_guard', 'reserve_queue', 'reserve_products'),
    ('save_dir', 'is_occupied', 'collision_check'),
]:
    patch_function(by_name[module], name, label)

original_guard = by_name['destination_guard'].guard_destinations
@contextmanager
def timed_guard(*args, **kwargs):
    ctx = original_guard(*args, **kwargs)
    with span('guard_preflight'):
        ctx.__enter__()
    try:
        yield
    except BaseException:
        with span('guard_release'):
            suppressed = ctx.__exit__(*sys.exc_info())
        if not suppressed:
            raise
    else:
        with span('guard_release'):
            ctx.__exit__(None, None, None)
by_name['destination_guard'].guard_destinations = timed_guard

Project = by_name['api'].Project
Project.submit = wrapped(Project.submit, 'total_submit')
Project.collect_results = staticmethod(wrapped(Project.collect_results, 'collect_results'))
Executor = by_name['parallel'].ParallelExecutor
Executor.__init__ = wrapped(Executor.__init__, 'executor_setup')
Executor.run = wrapped(Executor.run, 'executor_run')

instrumented = '--instrument' in sys.argv
if instrumented:
    sys.argv.remove('--instrument')
else:
    # Control driver imports the same modules but runs no timing wrappers.
    raise RuntimeError('Use --instrument; controls use the retained ordinary case driver')
output = Path(sys.argv[sys.argv.index('--output')+1])
driver = Path(__file__).resolve().parents[1]/'2026-10-08-process-preparation'/'case.py'
if '--driver' in sys.argv:
    index = sys.argv.index('--driver')
    driver = Path(sys.argv[index+1]).resolve()
    del sys.argv[index:index+2]
runpy.run_path(str(driver))['main']()
(output/'phase-timings.json').write_text(json.dumps(dict(metrics), indent=2)+'\n')
print(json.dumps(dict(event='phases', metrics=dict(metrics))), flush=True)
