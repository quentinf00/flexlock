"""Independent queue, local-product, source-record and timing verification."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import statistics
import subprocess
import xml.etree.ElementTree as ET

import yaml

RAW = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-compiled-guard-reuse')
OUT = Path(__file__).resolve().parent
LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
manifest = json.loads((RAW/'results.json').read_text())
assert len(manifest['runs']) == 17
references = {}
summary = {}
for fixture in ('plain', 'producer'):
    for variant in ('baseline', 'reuse'):
        rows = [r for r in manifest['runs'] if r['case'].startswith(fixture+'-')
                and r['case'].endswith('-'+variant)]
        assert len(rows) == 3
        summary[f'{fixture}-{variant}'] = dict(
            seconds=[r['seconds'] for r in rows],
            median=statistics.median(r['seconds'] for r in rows),
            executor_seconds=[r['guard_reuse']['executor_seconds'] for r in rows],
            executor_median=statistics.median(r['guard_reuse']['executor_seconds'] for r in rows),
            peak_rss_kib=[r['peak_rss_kib'] for r in rows])
    summary[fixture+'-reduction_percent'] = 100*(1-summary[fixture+'-reuse']['median']/summary[fixture+'-baseline']['median'])

for row in manifest['runs']:
    assert row['source_revision'] == manifest['revision']
    assert row['compilation']['selected_workers'] == 1
    count = row['count']
    baseline = row['guard_reuse']['baseline']
    assert row['guard_reuse']['merges']['compiler'] == count
    assert row['guard_reuse']['merges']['executor'] == (count if baseline else 0)
    if row['case'] == 'local-100':
        continue
    case = Path(row['output'])
    assert row['artifact_files'] == (2007 if count == 1000 else 207)
    assert row['details']['statuses'] == [['pending', count]]
    assert row['details']['scheduler_calls'] == 1
    with sqlite3.connect(f'file:{case}/runs/run.lock.tasks.db?mode=ro', uri=True) as db:
        values = [yaml.load(text.replace(str(case), '<CASE>'), Loader=LOADER)
                  for (text,) in db.execute('SELECT task_info FROM tasks')]
    values.sort(key=lambda c: c['item'])
    assert [c['item'] for c in values] == list(range(count))
    fixture = row['case'].split('-')[0]
    if fixture not in references:
        references[fixture] = values
    assert values == references[fixture], row['case']
    assert len(list((case/'runs').rglob('*.pkl'))) == 1
    scripts = list((case/'runs').rglob('*.slurm'))
    assert len(scripts) == 1 and '--array=0-3' in scripts[0].read_text()
    assert not list((case/'runs').rglob('product.json'))

local = next(r for r in manifest['runs'] if r['case'] == 'local-100')
assert local['details']['statuses'] == [['done', 100]]
products = list((Path(local['output'])/'runs').rglob('product.json'))
assert len(products) == 100
ids = []
for path in products:
    result = json.loads(path.read_text())
    ids.append(result['item'])
    assert result['sha256'] == hashlib.sha256((RAW.parent/'inputs'/f"{result['item']}.bin").read_bytes()).hexdigest()
assert sorted(ids) == list(range(100))

source_reference = None
source_commits = {}
for variant in ('baseline', 'reuse'):
    row = next(r for r in manifest['runs'] if r['case'] == 'source-'+variant)
    path = Path(row['output'])/'runs/run.lock'
    lock = yaml.load(path.read_text().replace(row['output'], '<CASE>'), Loader=LOADER)
    assert lock['repos']['main']['tree'] and lock['repos']['main']['include'] == ['benchmarks']
    assert not lock['repos']['main']['is_dirty']
    lock.pop('timestamp')
    commit = lock['repos']['main'].pop('commit')
    contents = subprocess.check_output(['git', 'cat-file', '-p', commit], text=True,
                                      cwd=lock['repos']['main']['path'])
    assert contents.splitlines()[0] == 'tree '+lock['repos']['main']['tree']
    assert contents.splitlines()[1] == 'parent '+manifest['revision']
    source_commits[variant] = dict(commit=commit, contents=contents)
    if source_reference is None:
        source_reference = lock
    assert lock == source_reference
    shutil.copyfile(path, OUT/f'source-{variant}-controller-lock.yaml')

tests = {}
for original, name in [('/tmp/flexlock-compiled-guard-tests.xml', 'guard-tests.xml'),
                       ('/tmp/flexlock-compiled-guard-submission.xml', 'submission-tests.xml')]:
    xml = Path(original).read_text()
    (OUT/name).write_text('\n'.join(line.rstrip() for line in xml.splitlines())+'\n')
    for case in ET.fromstring(xml).iter('testcase'):
        assert case.find('failure') is None and case.find('error') is None
        tests[(case.attrib['classname'], case.attrib['name'])] = 'skip' if case.find('skipped') is not None else 'pass'
validation = dict(equivalent_queues=16, equivalent_configs=14200,
                  normalized='Output-case prefix only; all config fields compared by item.',
                  verified_local_products=100, equivalent_source_content_records=2,
                  source_normalization='Output-case prefix, timestamp and generated shadow commit ID; commit trees and parents independently verified, original IDs retained.',
                  distinct_passes=sum(s == 'pass' for s in tests.values()),
                  distinct_skips=sum(s == 'skip' for s in tests.values()),
                  scheduler='mocked only', process_compilers=1,
                  file_count_1000=2007)
assert validation['distinct_passes'] == 161 and validation['distinct_skips'] == 2
for name, value in [('manifest.json', manifest), ('summary.json', summary), ('validation.json', validation),
                    ('source-commits.json', source_commits)]:
    (OUT/name).write_text(json.dumps(value, indent=2)+'\n')
print(json.dumps(dict(summary=summary, validation=validation), indent=2))
