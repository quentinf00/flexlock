"""Recompute timing summaries and check artifacts independently of submission."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import statistics

import yaml

LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)

RAW = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-process-preparation')
OUT = Path(__file__).resolve().parent
manifest = json.loads((RAW/'results.json').read_text())
assert len(manifest['runs']) == 22
references = {}
summary = {}
for fixture in ('plain', 'producer'):
    for workers in (1, 2, 4):
        rows = [r for r in manifest['runs'] if r['case'].startswith(fixture+'-')
                and r['requested_workers'] == workers]
        assert len(rows) == 3
        summary[f'{fixture}-{workers}'] = dict(
            seconds=[r['seconds'] for r in rows],
            median=statistics.median(r['seconds'] for r in rows),
            compile_seconds=[r['compilation']['compile_seconds'] for r in rows],
            compile_median=statistics.median(r['compilation']['compile_seconds'] for r in rows),
            child_cpu_seconds=[r['compilation']['child_cpu_seconds'] for r in rows],
            controller_peak_rss_kib=[r['peak_rss_kib'] for r in rows],
            child_peak_rss_kib=[r['compilation']['child_peak_rss_kib'] for r in rows])
        for row in rows:
            case = Path(row['output'])
            assert row['source_revision'] == manifest['revision']
            assert row['artifact_files'] == 2007
            assert row['details']['statuses'] == [['pending', 1000]]
            assert row['details']['scheduler_calls'] == 1
            with sqlite3.connect(f'file:{case}/runs/run.lock.tasks.db?mode=ro', uri=True) as db:
                values = [yaml.load(text.replace(str(case), '<CASE>'), Loader=LOADER)
                          for (text,) in db.execute('SELECT task_info FROM tasks')]
            values.sort(key=lambda c: c['item'])
            assert [c['item'] for c in values] == list(range(1000))
            if fixture not in references:
                references[fixture] = values
            assert values == references[fixture], row['case']
            assert len(list((case/'runs').rglob('*.pkl'))) == 1
            scripts = list((case/'runs').rglob('*.slurm'))
            assert len(scripts) == 1 and '--array=0-3' in scripts[0].read_text()
            assert not list((case/'runs').rglob('product.json'))

local = json.loads((RAW/'local-512-processes/measurement.json').read_text())
assert local['compilation']['selected_workers'] == 2
assert local['details']['statuses'] == [['done', 512]]
for name, count in [('local-100', 100), ('local-512-processes', 512)]:
    products = list((RAW/name/'runs').rglob('product.json'))
    assert len(products) == count
    ids = []
    for path in products:
        result = json.loads(path.read_text())
        ids.append(result['item'])
        assert result['sha256'] == hashlib.sha256((RAW.parent/'inputs'/f"{result['item']}.bin").read_bytes()).hexdigest()
    assert sorted(ids) == list(range(count))
for name in ('small-serial', 'small-optin', 'local-100'):
    row = next(r for r in manifest['runs'] if r['case'] == name)
    assert row['compilation']['selected_workers'] == 1

source = next(r for r in manifest['runs'] if r['case'] == 'source-1000')
assert source['compilation']['selected_workers'] == 2 and source['provenance']
lock = yaml.safe_load((Path(source['output'])/'runs/run.lock').read_text())
assert lock['repos']['main']['tree'] and lock['repos']['main']['include'] == ['benchmarks']
shutil.copyfile(Path(source['output'])/'runs/run.lock', OUT/'source-controller-lock.yaml')
for name, value in [('manifest.json', manifest), ('summary.json', summary), ('local-processes.json', local),
                    ('validation.json', dict(equivalent_queues=18, queued_items=18000,
                                            normalized='Output case prefix only; all config fields compared by item.',
                                            verified_local_products=612, local_process_items=512,
                                            scheduler='mocked only', default_processes=1))]:
    (OUT/name).write_text(json.dumps(value, indent=2)+'\n')
for original, name in [('/tmp/flexlock-process-acceptance.xml', 'compile-tests.xml'),
                       ('/tmp/flexlock-process-submission.xml', 'submission-tests.xml')]:
    (OUT/name).write_text('\n'.join(line.rstrip() for line in Path(original).read_text().splitlines())+'\n')
print(json.dumps(summary, indent=2))
