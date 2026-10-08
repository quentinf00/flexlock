"""Recompute preparation evidence from retained raw benchmark directories."""
import csv, hashlib, json, pstats, shutil, sqlite3, statistics
from pathlib import Path
import yaml

RAW = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark')
OUT = Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-08-freeze-binding-reuse')
OUT.mkdir(parents=True, exist_ok=True)
def emit(name, obj):
    (OUT/name).write_text(json.dumps(obj, indent=2)+'\n')

def queue(case):
    with sqlite3.connect(f'file:{case}/runs/run.lock.tasks.db?mode=ro', uri=True) as db:
        rows = db.execute('select task_info,status from tasks').fetchall()
    assert len(rows) == 1000 and all(status == 'pending' for _, status in rows)
    payloads = [yaml.safe_load(text.replace(str(case), '<CASE>')) for text, _ in rows]
    assert sorted(p['item'] for p in payloads) == list(range(1000))
    assert not list((case/'runs').rglob('product.json'))
    assert len(list((case/'runs').rglob('*.pkl'))) == 1
    scripts = list((case/'runs').rglob('*.slurm'))
    assert len(scripts) == 1 and '--array=0-3' in scripts[0].read_text()
    return sorted(payloads, key=lambda p: p['item'])

summary = {}
manifests = {}
for label, dirname in [('before', '2026-10-08-prep-slice1'), ('after', '2026-10-08-prep-slice2-fastpath')]:
    manifest = json.loads((RAW/dirname/'manifest.json').read_text())
    manifests[label] = manifest
    emit(label+'-manifest.json', manifest)
    values = [r['measurement'] for r in manifest['runs']]
    assert len(values) == 3 and all(r['exit_code'] == 0 for r in manifest['runs'])
    assert all(m['artifact_files'] == 2007 and m['details']['scheduler_calls'] == 1 for m in values)
    times = [m['seconds'] for m in values]
    summary[label] = dict(revision=manifest['source_revision'], seconds=times,
                         median=statistics.median(times), minimum=min(times), maximum=max(times),
                         peak_rss_kib=[m['peak_rss_kib'] for m in values], artifact_files=2007)
    assert all(m['source_revision'] == manifest['source_revision'] for m in values)
summary['median_reduction_percent'] = 100*(1-summary['after']['median']/summary['before']['median'])
reference = queue(Path(manifests['before']['runs'][0]['measurement']['output']))
for manifest in manifests.values():
    for run in manifest['runs']:
        assert queue(Path(run['measurement']['output'])) == reference

profiles = {}
for label, path in [('before', RAW/'2026-10-08-prep-slice1-profile/profile.pstats'),
                    ('after', RAW/'2026-10-08-prep-slice2-profile/profile.pstats')]:
    stats = pstats.Stats(str(path))
    funcs = {}
    for (filename, line, name), v in stats.stats.items():
        if (name in ('merge_task_into_cfg', 'bind_existing_run_locks', '_bind_detached_run_locks') and '/flexlock/' in filename) or (name == 'create' and filename.endswith('/omegaconf.py')):
            funcs[name] = dict(calls=v[1], cumulative_seconds=v[3], self_seconds=v[2], source=filename, line=line)
    funcs.setdefault('producer_binding', dict(calls=funcs.get('bind_existing_run_locks', funcs.get('_bind_detached_run_locks', {})).get('calls', 0)))
    profiles[label] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), profiler_total_seconds=stats.total_tt, functions=funcs)
emit('profiles.json', profiles)
source_manifest = json.loads((RAW/'2026-10-08-prep-slice2-source/manifest.json').read_text())
assert source_manifest['runs'][0]['exit_code'] == 0
source = source_manifest['runs'][0]['measurement']
assert source['provenance'] and source['count'] == 1000 and source['details']['statuses'] == [['pending', 1000]]
assert source['source_revision'] == summary['after']['revision']
emit('source-manifest.json', source_manifest)
summary['source_preparation_single_sample'] = source
local_root = RAW/'2026-10-08-prep-slice2-local'
local = json.loads((local_root/'measurement.json').read_text())
assert local['source_revision'] == summary['after']['revision']
products = list(local_root.rglob('product.json'))
assert len(products) == 100
ids = []
for path in products:
    p = json.loads(path.read_text())
    ids.append(p['item'])
    assert p['sha256'] == hashlib.sha256((RAW/'inputs'/f"{p['item']}.bin").read_bytes()).hexdigest()
assert sorted(ids) == list(range(100))
summary['local_smoke'] = local
emit('summary.json', summary)
with (OUT/'summary.csv').open('w') as f:
    writer = csv.writer(f, lineterminator='\n')
    writer.writerow(['variant', 'repeat', 'seconds', 'peak_rss_kib', 'artifact_files'])
    for label, manifest in manifests.items():
        for i, run in enumerate(manifest['runs']):
            m = run['measurement']
            writer.writerow([label, i, m['seconds'], m['peak_rss_kib'], m['artifact_files']])
shutil.copyfile('/tmp/flexlock-binding-reuse-tests/results.xml', OUT/'initial.xml')
shutil.copyfile('/tmp/flexlock-binding-reuse-tests/new-cases-recheck.xml', OUT/'new-cases-recheck.xml')
shutil.copyfile('/tmp/flexlock-binding-fastpath-tests/results.xml', OUT/'final-tests.xml')
emit('intermediate-manifest.json', json.loads((RAW/'2026-10-08-prep-slice2/manifest.json').read_text()))
# Normalize copied traceback whitespace; original XML remains in /tmp.
for xml in OUT.glob('*.xml'):
    xml.write_text('\n'.join(line.rstrip() for line in xml.read_text().splitlines())+'\n')
emit('validation.json', dict(all_six_queues_equivalent=True, normalization='Replace each case output prefix only; compare all parsed task payload fields by item. Task hashes differ with destination.',
     pending_items_per_queue=1000, scheduler_calls_per_case=1, worker_array='0-3', pickle_files_per_case=1,
     scheduler_products=0, local_products_sha256_verified=100, distinct_selected_test_cases_passing_across_runs=198,
     test_evidence='Initial copy-reuse acceptance: 184 passed, 12 new-fixture failures in legacy expected-path calculation. Corrected fixture: 12 passed. Final fast-path acceptance: 198 passed, including two additional regressions.',
     scope='Mocked scheduler; no production submission or installed consumer adoption.'))
print(json.dumps(summary, indent=2))
