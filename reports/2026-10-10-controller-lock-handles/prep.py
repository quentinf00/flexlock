"""Full preparation pairs with lightweight guard-only timing."""
from contextlib import contextmanager
from pathlib import Path
import json
import runpy
import sys
import time
from context import install_baseline
from flexlock import destination_guard
if '--baseline' in sys.argv:
    sys.argv.remove('--baseline')
    install_baseline()
original = destination_guard.guard_destinations
timings = dict(enter=0., release=0., calls=0)
@contextmanager
def timed_guard(*args, **kwargs):
    start = time.perf_counter()
    with original(*args, **kwargs) as value:
        timings['enter'] += time.perf_counter()-start
        timings['calls'] += 1
        try:
            yield value
        finally:
            release = time.perf_counter()
    timings['release'] += time.perf_counter()-release
destination_guard.guard_destinations = timed_guard
output=Path(sys.argv[sys.argv.index('--output')+1])
runpy.run_path(str(Path(__file__).resolve().parents[1]/'2026-10-08-process-preparation'/'case.py'))['main']()
p=output/'measurement.json'
r=json.loads(p.read_text());r['guard']=timings
p.write_text(json.dumps(r,indent=2)+'\n')
