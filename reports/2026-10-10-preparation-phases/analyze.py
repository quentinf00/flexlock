"""Validate nested accounting and equivalent queues; retain every run."""
import json
from pathlib import Path
import sqlite3
import statistics
import yaml

out=Path(__file__).resolve().parent
raw=Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-10-preparation-phases')
report=json.loads((raw/'results.json').read_text())
assert len(report['runs']) == 8
references={}
summary={}
for row in report['runs']:
    assert row['source_revision'] == report['revision']
    assert row['artifact_files'] == 2007 and row['details']['scheduler_calls'] == 1
    assert row['details']['statuses'] == [['pending',1000]]
    assert row['compilation']['selected_workers'] == 1
    case=Path(row['output'])
    with sqlite3.connect((case/'runs'/'run.lock.tasks.db').as_uri()+'?mode=ro',uri=True) as conn:
        configs=[yaml.load(text.replace(str(case),'<CASE>'),Loader=getattr(yaml,'CSafeLoader',yaml.SafeLoader)) for (text,) in conn.execute('SELECT task_info FROM tasks')]
    configs.sort(key=lambda cfg:cfg['item'])
    fixture=row['case'].split('-')[0]
    references.setdefault(fixture,configs)
    assert configs == references[fixture]
    if row['instrumented']:
        timing=row['timings']
        assert timing['main:task_hash']['calls'] == 5000
        assert timing['main:queue_yaml']['calls'] == 1000
        assert timing['main:sqlite_write_transaction']['calls'] == 1
        assert timing['io_workers:reservation_file']['calls'] == 1000
        exclusive=sum(v['exclusive_wall'] for k,v in timing.items() if k.startswith('main:'))
        assert abs(exclusive-timing['main:total_submit']['inclusive_wall']) < .05
for fixture in references:
    rows=[r for r in report['runs'] if r['case'].startswith(fixture) and r['instrumented']]
    assert len(rows) == 3
    keys=rows[0]['timings'].keys()
    summary[fixture]=dict(total_median=statistics.median(r['seconds'] for r in rows),
        phases={key:{field:statistics.median(r['timings'].get(key,{}).get(field,0) for r in rows)
                     for field in ('calls','inclusive_wall','exclusive_wall','inclusive_cpu','exclusive_cpu')}
                for key in keys})
validation=dict(equivalent_queues=8,equivalent_configs=8000,
                main_exclusive_accounting_verified=True,
                file_count=2007,scheduler='mocked only',runtime_changed=False)
for name,data in [('manifest.json',report),('summary.json',summary),('validation.json',validation)]:
    (out/name).write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps(dict(summary=summary,validation=validation),indent=2))
