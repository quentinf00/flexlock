"""Verify paired queues, input hashes, source trees and completed products."""
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import yaml
import xxhash

raw = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark')
inputs = raw/'inputs'
loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
summary = {}
validation = {}
for fixture, dirname, count, local in [
    ('preparation', '2026-10-11-source-grouping-isolated', 1000, False),
    ('worker', '2026-10-11-fingerprint-status-isolated', 100, True),
]:
    manifest = json.loads((raw/dirname/'results.json').read_text())
    assert len(manifest['runs']) == 6
    configs_ref = None
    fingerprint_ref = None
    trees = set()
    for row in manifest['runs']:
        assert row['source_revision'] == manifest['revision']
        assert row['details']['scheduler_calls'] == (0 if local else 1)
        assert row['details']['statuses'] == [['done' if local else 'pending', count]]
        assert row['artifact_files'] == (705 if local else 2007)
        case = Path(row['output'])
        with sqlite3.connect((case/'runs/run.lock.tasks.db').as_uri()+'?mode=ro',uri=True) as db:
            records = db.execute('SELECT task_info, snapshot, status FROM tasks').fetchall()
        configs = [yaml.load(text.replace(str(case), '<CASE>'), Loader=loader) for text, _, _ in records]
        configs.sort(key=lambda t:t['item'])
        if configs_ref is None:
            configs_ref = configs
        assert configs == configs_ref
        assert all(t['_snapshot_']['data']['input'] == str(inputs/f'{i}.bin') for i,t in enumerate(configs))
        master = yaml.load((case/'runs/run.lock').read_text(), Loader=loader)
        trees.add(master['repos']['main']['tree'])
        assert master['data']['input'] == xxhash.xxh64((inputs/'0.bin').read_bytes()).hexdigest()
        cache = case.with_name(case.name+'-hash-cache')/'flexlock/hashes_v2.db'
        assert cache.exists()
        with sqlite3.connect(cache.as_uri()+'?mode=ro',uri=True) as db:
            cached_paths = {p for (p,) in db.execute('SELECT path FROM cache')}
        assert cached_paths == {str(inputs/f'{i}.bin') for i in range(count if local else 1)}
        if local:
            fingerprints = {}
            for text, snapshot, status in records:
                task = yaml.load(text, Loader=loader)
                snap = json.loads(snapshot)
                i = task['item']
                product = Path(task['save_dir'])
                expected = hashlib.sha256((inputs/f'{i}.bin').read_bytes()).hexdigest()
                assert json.loads((product/'product.json').read_text()) == dict(item=i, sha256=expected)
                assert (product/'run.complete').exists()
                lock = yaml.load((product/'run.lock').read_text(), Loader=loader)
                for receipt in (snap, lock):
                    assert receipt['data']['input'] == xxhash.xxh64((inputs/f'{i}.bin').read_bytes()).hexdigest()
                    assert receipt['data_identity']['input']['path'] == str(inputs/f'{i}.bin')
                    assert receipt['repos']['main']['tree'] == master['repos']['main']['tree']
                    assert not receipt.get('code_drift')
                    assert receipt['fingerprint']
                fingerprints[i] = lock['fingerprint']
            if fingerprint_ref is None:
                fingerprint_ref = fingerprints
            assert fingerprints == fingerprint_ref
            assert row['source_work']['tree_calls'] == count
            assert row['source_work']['status_calls'] == (count+1 if row['baseline'] else 1)
        else:
            assert row['repo_collection']['merges'] == (count if row['baseline'] else 1)
    assert len(trees) == 1
    summary[fixture] = dict(manifest=manifest, medians={})
    for baseline in (True, False):
        runs = [r for r in manifest['runs'] if r['baseline'] == baseline]
        group = 'baseline' if baseline else 'current'
        details = 'source_work' if local else 'repo_collection'
        summary[fixture]['medians'][group] = dict(total_seconds=statistics.median(r['seconds'] for r in runs),
            **{k:statistics.median(r[details][k] for r in runs) for k in runs[0][details]})
    validation[fixture] = dict(equivalent_queues=6, equivalent_configs=count*6,
        products_verified=count*6 if local else 0, matching_source_trees=True,
        master_input_hash_verified=True, per_item_paths_verified=True,
        isolated_caches_verified=True, fingerprints_match=True if local else None)
out = Path(__file__).resolve().parent
out.mkdir(exist_ok=True)
for name,data in [('summary.json',summary),('validation.json',validation)]:
    (out/name).write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps(dict(medians={k:v['medians'] for k,v in summary.items()},validation=validation),indent=2))
