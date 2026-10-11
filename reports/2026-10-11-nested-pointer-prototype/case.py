"""Report-only nested-pointer experiment; current writers are unchanged."""
from pathlib import Path
import json
import os
import runpy
import sys

output = Path(sys.argv[sys.argv.index('--output')+1])
os.environ['FLEXLOCK_CACHE'] = str(output.with_name(output.name+'-hash-cache'))
os.environ['FLEXLOCK_INDEX'] = str(output/'index.db')
from flexlock import destination_guard
if '--omit-nested-pointers' in sys.argv:
    sys.argv.remove('--omit-nested-pointers')
    original = destination_guard.reserve_queue
    def reserve_external(paths, db_path):
        root = Path(db_path).resolve().parent
        retained = [p for p in paths if not Path(p).resolve().is_relative_to(root)
                    or (Path(p)/destination_guard.QUEUE_POINTER).exists()]
        return original(retained, db_path)
    destination_guard.reserve_queue = reserve_external
runpy.run_path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-11-tracked-preparation/case.py')['main']()
