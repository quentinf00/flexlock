"""Tracked local execution; baseline computes the discarded dirty flag."""
import importlib
import json
from pathlib import Path
import runpy
import sys
import time
from git.repo import Repo
from flexlock.git_utils import create_shadow_tree

module = importlib.import_module('flexlock.fingerprint')
if '--baseline' in sys.argv:
    sys.argv.remove('--baseline')
    def with_status(path, include=None, exclude=None, *, check_dirty):
        return create_shadow_tree(path, include, exclude)
    module._create_shadow_tree = with_status
metrics = dict(tree_calls=0, tree_seconds=0., status_calls=0, status_seconds=0.)
original_tree = module._repo_tree
original_status = Repo.is_dirty
def timed_tree(*args, **kwargs):
    start = time.perf_counter()
    try:
        return original_tree(*args, **kwargs)
    finally:
        metrics['tree_calls'] += 1
        metrics['tree_seconds'] += time.perf_counter()-start
def timed_status(*args, **kwargs):
    start = time.perf_counter()
    try:
        return original_status(*args, **kwargs)
    finally:
        metrics['status_calls'] += 1
        metrics['status_seconds'] += time.perf_counter()-start
module._repo_tree = timed_tree
Repo.is_dirty = timed_status
runpy.run_path(str(Path(__file__).with_name('case.py')))['main']()
output = Path(sys.argv[sys.argv.index('--output')+1])
path = output/'measurement.json'
result = json.loads(path.read_text())
result['source_work'] = metrics
path.write_text(json.dumps(result, indent=2)+'\n')
