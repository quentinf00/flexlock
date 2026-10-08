"""Recompute preparation I/O comparison and independently verify queue payloads."""
import csv, hashlib, json, shutil, sqlite3, statistics
from pathlib import Path
import yaml
RAW=Path('/ontap/user/qfebvre/flexlock-hydra-benchmark')
OUT=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-08-preparation-io')
OUT.mkdir(parents=True,exist_ok=True)
def emit(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n')
manifest=json.loads((RAW/'2026-10-08-prep-io-comparison/manifest.json').read_text())
assert len(manifest['runs'])==12
emit('comparison-manifest.json',manifest)
summary={}
reference=None
for variant in ['original','io-1','io-2','io-4']:
    rows=[r for r in manifest['runs'] if r['variant']==variant]
    assert len(rows)==3
    measurements=[r['measurement'] for r in rows]
    summary[variant]=dict(seconds=[m['seconds'] for m in measurements],
        median=statistics.median(m['seconds'] for m in measurements),
        peak_rss_kib=[m['peak_rss_kib'] for m in measurements],
        phase_medians={key:statistics.median(r['wall_clock_phases'][key]['seconds'] for r in rows) for key in rows[0]['wall_clock_phases']})
    for row in rows:
        m=row['measurement'];assert row['exit_code']==0 and m['source_revision']==manifest['source_revision']
        assert m['artifact_files']==2007 and m['details']['scheduler_calls']==1
        assert m['details']['statuses']==[['pending',1000]]
        case=Path(m['output'])
        with sqlite3.connect(f'file:{case}/runs/run.lock.tasks.db?mode=ro',uri=True) as db:
            payloads=[yaml.safe_load(p.replace(str(case),'<CASE>')) for (p,) in db.execute('SELECT task_info FROM tasks')]
        payloads.sort(key=lambda p:p['item'])
        assert [p['item'] for p in payloads]==list(range(1000))
        if reference is None:reference=payloads
        assert payloads==reference
        scripts=list((case/'runs').rglob('*.slurm'))
        assert len(scripts)==1 and '--array=0-3' in scripts[0].read_text()
        assert len(list((case/'runs').rglob('*.pkl')))==1
        assert not list((case/'runs').rglob('product.json'))
summary['median_reduction_percent']=100*(1-summary['io-2']['median']/summary['original']['median'])
emit('summary.json',summary)
with (OUT/'summary.csv').open('w') as f:
    writer=csv.writer(f,lineterminator='\n')
    writer.writerow(['variant','repeat','seconds','guard_entry','reservation_write'])
    for r in manifest['runs']:
        writer.writerow([r['variant'],r['repeat'],r['measurement']['seconds'],r['wall_clock_phases']['guard_entry']['seconds'],r['wall_clock_phases']['reservation_write']['seconds']])
for dirname,filename in [('flexlock-prep-io-tests','initial-tests.xml'),('flexlock-prep-io-default-tests','default-tests.xml')]:
    shutil.copyfile(Path('/tmp')/dirname/'results.xml',OUT/filename)
for original,copy in [('io-recheck.xml','fixture-error.xml'),('io-final.xml','io-tests.xml')]:
    xml=(Path('/tmp/flexlock-prep-io-tests')/original).read_text()
    (OUT/copy).write_text('\n'.join(line.rstrip() for line in xml.splitlines())+'\n')
for source,name in [('/tmp/preparation_io_matrix.py','io_matrix.py'),('/tmp/preparation_phase_timers.py','phase_timers.py'),('/tmp/flexlock-prep-io-baseline.py','baseline_guard.py')]:
    shutil.copyfile(source,OUT/name)
local_root=RAW/'2026-10-08-prep-io-default-local'
local=json.loads((local_root/'measurement.json').read_text())
products=list(local_root.rglob('product.json'));assert len(products)==100
ids=[]
for path in products:
    p=json.loads(path.read_text());ids.append(p['item'])
    assert p['sha256']==hashlib.sha256((RAW/'inputs'/f"{p['item']}.bin").read_bytes()).hexdigest()
assert sorted(ids)==list(range(100))
emit('local-smoke.json',local)
source_manifest=json.loads((RAW/'2026-10-08-prep-io-default-source/manifest.json').read_text())
emit('source-manifest.json',source_manifest)
assert source_manifest['runs'][0]['exit_code']==0
assert source_manifest['runs'][0]['measurement']['provenance']
shutil.copyfile(Path(source_manifest['runs'][0]['measurement']['output'])/'runs/run.lock',OUT/'source-controller-lock.yaml')
emit('default-measurement.json',json.loads((RAW/'2026-10-08-prep-io-default/measurement.json').read_text()))
emit('validation.json',dict(equivalent_queues=12,items_per_queue=1000,normalized='Output case prefix only; compare all fields by item.',
    local_sha256_products=100,scheduler='mocked only',default_io_workers=2,
    test_scope='Focused tests; injected failures join outstanding operations under held locks, no scheduler on reservation failure; legacy and cross-tag guards retained.'))
print(json.dumps(summary,indent=2))
