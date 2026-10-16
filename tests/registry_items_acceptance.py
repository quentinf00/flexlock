"""Opt-in local T5 campaign acceptance; no scheduler or scientific data needed.

Run with the selected checkout in PYTHONPATH and a fresh output-root argument.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flexlock import Project
from flexlock.record import list_task_records, load_record
from flexlock.registry import initialize, diagnose
from tests.test_registry_items import config


def main():
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    initialize(root)
    cfg = config(root)
    cfg._snapshot_.repos = {'flexlock': str(ROOT)}
    first = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}], n_jobs=1,
                             task_record='db',  note='T5 serial acceptance')
    before = [(Path(r.record_dir)/'run.complete').read_bytes() for r in first]
    appended = Project().submit(cfg, sweep=[{'item': 1}, {'item': 2}, {'item': 3}],
                                n_jobs=1, task_record='db', note='T5 append acceptance')
    assert [r.status for r in appended] == ['SUCCESS', 'SUCCESS', 'SUCCESS']
    assert before == [(Path(r.record_dir)/'run.complete').read_bytes() for r in first]
    assert all(load_record(r.record_dir)['note'] == 'T5 serial acceptance' for r in first)
    parallel_cfg = cfg.copy(); parallel_cfg.save_dir = str(root/'parallel-products')
    parallel = Project().submit(parallel_cfg, sweep=[{'item': 1}, {'item': 2}],
                                n_jobs=2, task_record='dir',
                                sweep_root=str(root/'parallel-campaign'))
    assert [r.get('item') for r in parallel] == [1, 2]
    assert all(r.is_success for r in parallel)
    bad_cfg = cfg.copy(); bad_cfg.save_dir = str(root/'failure-products')
    failure = Project().submit(bad_cfg, sweep=[{'item': 1, 'fail': True}, {'item': 2}],
                               n_jobs=1, task_record='db',
                               sweep_root=str(root/'failure-campaign'))
    assert [r.status for r in failure] == ['FAILED', 'SUCCESS']
    entries = list_task_records(appended[-1].task_db, check_outputs=True)
    assert len(entries) == 3 and all(e['artifact_health'] == 'valid' for e in entries)
    result = dict(passed=True, source_head=subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        python=sys.executable, registry=diagnose(root),
        serial_then_append=[dict(task_id=r.task_id, status=r.status,
                                 product_dir=r.save_dir, record_dir=r.record_dir,
                                 database=r.task_db, result=r.result) for r in appended],
        parallel=[dict(task_id=r.task_id, record_dir=r.record_dir, result=r.result) for r in parallel],
        failure=[dict(task_id=r.task_id, status=r.status, record_dir=r.record_dir) for r in failure],
        logical_items=entries)
    (root/'acceptance.json').write_text(json.dumps(result, indent=2, default=str)+'\n')
    print(json.dumps(dict(passed=True, items=len(entries), root=str(root))))


if __name__ == '__main__':
    main()
