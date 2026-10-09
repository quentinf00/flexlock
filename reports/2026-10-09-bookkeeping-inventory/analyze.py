"""Verify prototype config equivalence and compute the retained comparison."""
import json
from pathlib import Path
import sqlite3
import statistics

import yaml

RAW = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-09-bookkeeping-inventory')
OUT = Path(__file__).resolve().parent
manifest = json.loads((RAW/'results.json').read_text())
assert len(manifest['runs']) == 6
reference = None
summary = {}
loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
for prototype in (False, True):
    rows = [r for r in manifest['runs'] if r['prototype'] == prototype]
    summary['omit' if prototype else 'current'] = dict(
        seconds=[r['seconds'] for r in rows], median=statistics.median(r['seconds'] for r in rows),
        files=[r['artifact_files'] for r in rows])
    for row in rows:
        assert row['source_revision'] == manifest['revision']
        assert row['compilation']['selected_workers'] == 1
        assert row['artifact_files'] == (1007 if prototype else 2007)
        assert row['details']['statuses'] == [['pending', 1000]]
        assert row['details']['scheduler_calls'] == 1
        case = Path(row['output'])
        with sqlite3.connect(f'file:{case}/runs/run.lock.tasks.db?mode=ro', uri=True) as db:
            values = [yaml.load(text.replace(str(case), '<CASE>'), Loader=loader)
                      for (text,) in db.execute('SELECT task_info FROM tasks')]
        values.sort(key=lambda c: c['item'])
        assert [v['item'] for v in values] == list(range(1000))
        if reference is None:
            reference = values
        assert values == reference
        assert len(list((case/'runs').rglob('.flexlock-controller.lock'))) == 1001
        assert len(list((case/'runs').rglob('.flexlock-queue.json'))) == (0 if prototype else 1000)
        assert not list((case/'runs').rglob('product.json'))
summary['median_reduction_percent'] = 100*(1-summary['omit']['median']/summary['current']['median'])
for name, value in [('manifest.json', manifest), ('summary.json', summary),
                    ('validation.json', dict(equivalent_configs=6000, equivalent_queues=6,
                                             normalization='Output case prefix only.',
                                             scheduler='mocked only', default_adoption=False,
                                             reason='Unchanged producer reader permits stale binding without a nested pointer.'))]:
    (OUT/name).write_text(json.dumps(value, indent=2)+'\n')
print(json.dumps(summary, indent=2))
