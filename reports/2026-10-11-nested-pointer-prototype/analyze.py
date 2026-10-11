"""Compare prepared configs and reservations using their actual compiled paths."""
import json
from pathlib import Path
import sqlite3
import statistics
import yaml
import xxhash
from flexlock.destination_guard import has_active_destination, QUEUE_POINTER, CONTROLLER_LOCK

raw=Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-11-pointer-experiment')
report=json.loads((raw/'results.json').read_text())
refs=[]; trees=set()
assert len(report['runs']) == 6
for row in report['runs']:
    case=Path(row['output'])
    assert row['source_revision'] == report['revision']
    assert row['artifact_files'] == (1007 if row['omit'] else 2007)
    assert row['details']['statuses'] == [['pending',1000]]
    assert row['details']['scheduler_calls'] == 1
    assert len(list(case.rglob(QUEUE_POINTER))) == (0 if row['omit'] else 1000)
    assert len(list(case.rglob(CONTROLLER_LOCK))) == 1001
    db=case/'runs/run.lock.tasks.db'; before=db.read_bytes()
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
        cfgs=[yaml.load(t.replace(str(case),'<CASE>'),Loader=yaml.CSafeLoader)
              for (t,) in conn.execute('SELECT task_info FROM tasks')]
    cfgs.sort(key=lambda c:c['item']); refs.append(cfgs)
    master=yaml.load((case/'runs/run.lock').read_text(),Loader=yaml.CSafeLoader)
    trees.add(master['repos']['main']['tree'])
    assert master['data']['input'] == xxhash.xxh64(Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs/0.bin').read_bytes()).hexdigest()
    for i in (0,499,999):
        product=Path(cfgs[i]['save_dir'].replace('<CASE>',str(case)))
        assert has_active_destination(product)
        assert (product/QUEUE_POINTER).exists() != row['omit']
    assert db.read_bytes() == before
assert all(r == refs[0] for r in refs)
assert len(trees) == 1
summary={name:statistics.median(r['seconds'] for r in report['runs'] if r['omit']==omit)
         for name,omit in [('current',False),('omit',True)]}
result=dict(manifest=report,medians=summary,validation=dict(equivalent_queues=6,
    equivalent_configs=6000,source_trees_match=True,master_input_hash_verified=True,
    active_replacements_detected=True,queues_unchanged_by_reader=True,
    files_current=2007,files_prototype=1007,mutexes_preserved=1001,default_writer_changed=False))
Path(__file__).with_name('summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='manifest'},indent=2))
