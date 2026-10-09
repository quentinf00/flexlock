"""Binding costs for complete producer cohorts and queued future cohorts."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time

from omegaconf import OmegaConf
from flexlock.destination_guard import reserve_queue
from flexlock.resolvers import bind_existing_run_locks
from flexlock.run_record import RunRecord
from flexlock.taskdb import queue_tasks
from context import install_baseline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--future', action='store_true')
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    if args.baseline:
        install_baseline()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    db = root/'queue'/'run.lock.tasks.db'
    products = [db.parent/'products'/str(i) for i in range(1000)]
    tasks = [dict(save_dir=str(p), item=i) for i, p in enumerate(products)]
    queue_tasks(db, tasks)
    if not args.future:
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE tasks SET status='done'")
    reserve_queue(products, db)
    for i, product in enumerate(products):
        RunRecord(product).write_lock(dict(config=dict(value=['literal ${missing}', dict(item=i)]), timestamp='fixed'))
    indices = range(0, 1000, 10) if args.future else range(1000)
    configs = [OmegaConf.create(dict(value='${run_lock:'+str(products[i])+',config.value}')) for i in indices]
    start = time.perf_counter()
    bound = [bind_existing_run_locks(cfg, allow_future=args.future) for cfg in configs]
    seconds = time.perf_counter()-start
    values = [OmegaConf.to_container(cfg, resolve=False) for cfg in bound]
    if args.future:
        assert all(v['value'] == '${run_lock:'+str(products[i])+',config.value}' for i, v in zip(indices, values))
        assert all(not v.get('_snapshot_', {}).get('run_lock_reads') for v in values)
    else:
        assert all(v['_snapshot_']['run_lock_reads'][0]['binding'] == 'submit' for v in values)
    encoded = json.dumps(values, sort_keys=True).replace(str(root), '<CASE>').encode()
    result = dict(seconds=seconds, count=len(configs), queue_items=1000,
                  baseline=args.baseline, future=args.future,
                  payload_sha256=hashlib.sha256(encoded).hexdigest(),
                  revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip())
    (root/'measurement.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
