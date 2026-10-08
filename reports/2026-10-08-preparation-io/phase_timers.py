"""Unprofiled wall-clock diagnostics; nested timers overlap, not additive."""
import argparse
from collections import defaultdict
from contextlib import contextmanager
import functools
import json
from pathlib import Path
import time

from benchmarks.thousand_items import measure
from flexlock import api, parallel, record, freeze, utils, destination_guard

metrics = defaultdict(lambda: dict(calls=0, seconds=0.0))
def add(name, elapsed):
    metrics[name]['calls'] += 1
    metrics[name]['seconds'] += elapsed

def wrap(owner, attribute, name, static=False):
    original = getattr(owner, attribute)
    @functools.wraps(original)
    def timed(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            add(name, time.perf_counter()-start)
    setattr(owner, attribute, staticmethod(timed) if static else timed)

wrap(utils, 'merge_task_into_cfg', 'merge')
wrap(freeze, '_freeze_and_bind', 'freeze_bind')
wrap(record, '_list_task_records', 'record_selection_materialization')
wrap(parallel, 'queue_tasks', 'queue_insert')
wrap(destination_guard, 'reserve_queue', 'reservation_write')
wrap(parallel.ParallelExecutor, '__init__', 'executor_constructor')
wrap(parallel.ParallelExecutor, 'run', 'executor_run')
wrap(api.Project, 'collect_results', 'collect_results', static=True)
wrap(api.Project, '_submit_sweep', 'submit_sweep_total')
original_guard = destination_guard.guard_destinations
@contextmanager
def timed_guard(*args, **kwargs):
    enter_start = time.perf_counter()
    exit_start = None
    try:
        with original_guard(*args, **kwargs):
            add('guard_entry', time.perf_counter()-enter_start)
            try:
                yield
            finally:
                exit_start = time.perf_counter()
    finally:
        if exit_start is not None:
            add('guard_exit', time.perf_counter()-exit_start)
destination_guard.guard_destinations = timed_guard

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--count', type=int, default=1000)
    args = parser.parse_args()
    measure.run(argparse.Namespace(kind='flexlock-slurm', count=args.count,
        output=args.output, inputs=args.inputs, provenance=False, data=False,
        cache_search=False, record='dir', batch=1, profile=False))
    (Path(args.output)/'wall-clock-phases.json').write_text(json.dumps(dict(metrics), indent=2)+'\n')
    print(json.dumps(dict(metrics)), flush=True)
