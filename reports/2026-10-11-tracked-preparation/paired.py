"""Matched source/data controls with controller repository-collection timing."""
from pathlib import Path
import json
import runpy
import sys
import time
import os

# Some FlexLock imports initialize the hash-cache path. Isolate before imports.
output = Path(sys.argv[sys.argv.index('--output')+1])
os.environ['FLEXLOCK_CACHE'] = str(output.with_name(output.name+'-hash-cache'))
os.environ['FLEXLOCK_INDEX'] = str(output/'index.db')
from flexlock import utils, parallel

if '--baseline' in sys.argv:
    sys.argv.remove('--baseline')
    source = Path(__file__).with_name('baseline_collect.py').read_text()
    namespace = vars(utils)
    exec(compile(source, 'baseline_collect.py', 'exec'), namespace)
original = utils.collect_task_repos
metrics = dict(seconds=0., calls=0, merges=0)
merge = utils.merge_task_into_cfg
def counted_merge(*args, **kwargs):
    metrics['merges'] += 1
    return merge(*args, **kwargs)
def timed_collect(*args, **kwargs):
    start = time.perf_counter()
    utils.merge_task_into_cfg = counted_merge
    try:
        return original(*args, **kwargs)
    finally:
        utils.merge_task_into_cfg = merge
        metrics['seconds'] += time.perf_counter()-start
        metrics['calls'] += 1
utils.collect_task_repos = parallel.collect_task_repos = timed_collect
runpy.run_path(str(Path(__file__).with_name('case.py')))['main']()
output = Path(sys.argv[sys.argv.index('--output')+1])
path = output/'measurement.json'
result = json.loads(path.read_text())
result['repo_collection'] = metrics
path.write_text(json.dumps(result, indent=2)+'\n')
