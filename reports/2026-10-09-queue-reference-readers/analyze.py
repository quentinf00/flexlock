"""Verify benchmark equivalence and retain the now-fixed stale-binding case."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import statistics
import tempfile

import yaml
from omegaconf import OmegaConf
from omegaconf.errors import InterpolationResolutionError
from flexlock import destination_guard
from flexlock.resolvers import bind_existing_run_locks
from flexlock.run_record import RunRecord
from flexlock.taskdb import queue_tasks

OUT = Path(__file__).resolve().parent
RAW = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-09-queue-reference-readers')
manifest = json.loads((RAW/'results.json').read_text())
assert len(manifest['runs']) == 18
summary = {}
for fixture in ('prep', 'terminal', 'future'):
    for variant in ('baseline', 'current'):
        rows = [r for r in manifest['runs'] if r['case'].startswith(fixture+'-')
                and r['case'].endswith('-'+variant)]
        assert len(rows) == 3
        summary[fixture+'-'+variant] = dict(seconds=[r['seconds'] for r in rows],
                                          median=statistics.median(r['seconds'] for r in rows))

reference = None
hashes = {}
for row in manifest['runs']:
    assert row.get('revision', row.get('source_revision')) == manifest['revision']
    fixture = row['case'].split('-')[0]
    if fixture != 'prep':
        assert row['queue_items'] == 1000
        assert row['count'] == (100 if fixture == 'future' else 1000)
        hashes.setdefault(fixture, row['payload_sha256'])
        assert row['payload_sha256'] == hashes[fixture]
        continue
    assert row['artifact_files'] == 2007 and row['compilation']['selected_workers'] == 1
    assert row['details']['scheduler_calls'] == 1 and row['details']['statuses'] == [['pending', 1000]]
    case = Path(row['output'])
    with sqlite3.connect(f'file:{case}/runs/run.lock.tasks.db?mode=ro', uri=True) as db:
        payloads = [yaml.load(p.replace(str(case), '<CASE>'), Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))
                    for (p,) in db.execute('SELECT task_info FROM tasks')]
    payloads.sort(key=lambda cfg: cfg['item'])
    if reference is None:
        reference = payloads
    assert payloads == reference

spec = importlib.util.spec_from_file_location('flexlock._reference_check', OUT/'baseline_guard.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
with tempfile.TemporaryDirectory(prefix='flexlock-fixed-binding-') as tmp:
    root = Path(tmp)
    product = root/'queue'/'nested'/'product'
    RunRecord(product).write_lock(dict(config=dict(value=41), timestamp='old'))
    queue_tasks(root/'queue'/'run.lock.tasks.db', [dict(save_dir=str(product))])
    assert not baseline.has_active_destination(product)
    assert destination_guard.has_active_destination(product)
    cfg = OmegaConf.create(dict(value='${run_lock:'+str(product)+',config.value}'))
    try:
        bind_existing_run_locks(cfg)
    except InterpolationResolutionError as exc:
        assert 'pending/running work' in str(exc)
    else:
        raise AssertionError('stale artifact was bound')
    future = bind_existing_run_locks(cfg, allow_future=True)
    assert OmegaConf.to_container(future, resolve=False)['value'] == '${run_lock:'+str(product)+',config.value}'

validation = dict(prepared_queues=6, equivalent_queue_configs=6000,
                  equivalent_completed_bindings=6000, equivalent_future_bindings=600,
                  old_counterexample_reproduced=True, current_stale_binding_rejected=True,
                  exact_future_path_preserved=True, prepared_files=2007,
                  writers_changed=False, scheduler='mocked only')
for name, value in [('manifest.json', manifest), ('summary.json', summary), ('validation.json', validation)]:
    (OUT/name).write_text(json.dumps(value, indent=2)+'\n')
for source, name in [('/tmp/flexlock-queue-refs-final.xml', 'final-tests.xml'),
                     ('/tmp/flexlock-queue-refs-legacy.xml', 'legacy-tests.xml')]:
    text = Path(source).read_text()
    (OUT/name).write_text('\n'.join(line.rstrip() for line in text.splitlines())+'\n')
print(json.dumps(dict(summary=summary, validation=validation), indent=2))
