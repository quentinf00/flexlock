"""Verify all prepared payloads and independently check local products."""
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import yaml

out=Path(__file__).resolve().parent
raw=Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-10-controller-lock-handles')
report=json.loads((raw/'results.json').read_text())
assert len(report['runs']) == 12
refs={}
summary={}
for row in report['runs']:
    assert row['source_revision'] == report['revision']
    assert row['artifact_files'] == 2007 and row['details']['scheduler_calls'] == 1
    assert row['details']['statuses'] == [['pending',1000]]
    assert row['compilation']['selected_workers'] == 1 and row['guard']['calls'] == 1
    case=Path(row['output'])
    with sqlite3.connect((case/'runs'/'run.lock.tasks.db').as_uri()+'?mode=ro',uri=True) as conn:
        configs=[yaml.load(text.replace(str(case),'<CASE>'),Loader=getattr(yaml,'CSafeLoader',yaml.SafeLoader)) for (text,) in conn.execute('SELECT task_info FROM tasks')]
    configs.sort(key=lambda cfg:cfg['item'])
    fixture=row['case'].split('-')[0]
    refs.setdefault(fixture,configs)
    assert configs == refs[fixture]
for fixture in refs:
    summary[fixture]={}
    for variant in ('baseline','current'):
        rows=[r for r in report['runs'] if r['case'].startswith(fixture) and r['case'].endswith(variant)]
        assert len(rows) == 3
        summary[fixture][variant]=dict(seconds=[r['seconds'] for r in rows],
            total_median=statistics.median(r['seconds'] for r in rows),
            enter_median=statistics.median(r['guard']['enter'] for r in rows),
            release_median=statistics.median(r['guard']['release'] for r in rows))
local=json.loads((raw/'local-smoke'/'measurement.json').read_text())
assert local['details']['statuses'] == [['done',10]] and local['details']['scheduler_calls'] == 0
products=list((raw/'local-smoke'/'runs').glob('sweep_*/product.json'))
assert len(products) == 10
for path in products:
    product=json.loads(path.read_text())
    expected=hashlib.sha256((Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs')/f"{product['item']}.bin").read_bytes()).hexdigest()
    assert product['sha256'] == expected
    assert (path.parent/'run.complete').exists()
validation=dict(equivalent_queues=12,equivalent_configs=12000,
                local_products_verified=10,prepared_file_count=2007,
                scheduler='mocked only',format_changed=False)
for name,data in [('manifest.json',report),('summary.json',summary),('validation.json',validation),('local-smoke.json',local)]:
    (out/name).write_text(json.dumps(data,indent=2)+'\n')
text=Path('/tmp/flexlock-lock-handles-tests.xml').read_text()
(out/'tests.xml').write_text('\n'.join(line.rstrip() for line in text.splitlines())+'\n')
print(json.dumps(dict(summary=summary,validation=validation),indent=2))
