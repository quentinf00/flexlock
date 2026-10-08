"""Compare guard reuse on frozen source; process compilation stays disabled."""
import json
from pathlib import Path
import runpy
import sys
import time

from flexlock.parallel import ParallelExecutor
import flexlock.utils as utils


def main():
    baseline = '--baseline' in sys.argv
    if baseline:
        sys.argv.remove('--baseline')
    merges = dict(compiler=0, executor=0, other=0)
    phase = 'compiler'
    diagnostics = {}
    merge = utils.merge_task_into_cfg
    initialize = ParallelExecutor.__init__

    def counted_merge(*args, **kw):
        merges[phase] += 1
        return merge(*args, **kw)

    def counted_initialize(self, *args, **kw):
        nonlocal phase
        if baseline:
            kw['_compiled_tasks'] = False
        phase = 'executor'
        start = time.perf_counter()
        try:
            return initialize(self, *args, **kw)
        finally:
            diagnostics['executor_seconds'] = time.perf_counter()-start
            phase = 'other'

    utils.merge_task_into_cfg = counted_merge
    ParallelExecutor.__init__ = counted_initialize
    driver = Path(__file__).resolve().parents[1]/'2026-10-08-process-preparation'/'case.py'
    runpy.run_path(str(driver))['main']()
    output = Path(sys.argv[sys.argv.index('--output')+1])
    path = output/'measurement.json'
    result = json.loads(path.read_text())
    result['guard_reuse'] = dict(baseline=baseline, merges=merges, **diagnostics)
    path.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(output=str(output), **result['guard_reuse'])), flush=True)


if __name__ == '__main__':
    main()
