"""One bulk queue export from an explicit manifest; coverage is project-owned."""
import argparse
import hashlib
import json
from pathlib import Path

import yaml
from flexlock import py2cfg
from flexlock.record import load_record
from flexlock.exceptions import FlexLockError
from omegaconf import OmegaConf
from examples.slimmer_workflows.stages import process


def read_manifest(path):
    rows = json.loads(Path(path).read_text())
    ids = [row['item_id'] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate manifest item IDs')
    for row in rows:
        if not row['item_id'] or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in row['item_id']):
            raise ValueError('Use simple, nonempty item IDs; never derive output paths from untrusted IDs')
        if row['disposition'] not in ('process', 'excluded'):
            raise ValueError('Unknown manifest disposition')
        if row['disposition'] == 'excluded' and not row.get('reason'):
            raise ValueError('An exclusion needs a reason')
    return rows


def export_queue(manifest, root, queue):
    rows = read_manifest(manifest)
    configs = []
    for row in rows:
        if row['disposition'] == 'excluded':
            continue
        source = Path(row['input_path']).resolve()
        if hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f"Input changed: {source}")
        config = py2cfg(process, item_id=row['item_id'], input_path=str(source),
            expected_sha256=row['sha256'],
            save_dir=str(Path(root).resolve() / 'items' / row['item_id']),
            _snapshot_=dict(repos={}, data=dict(input=str(source), manifest=str(Path(manifest).resolve()))),
            _outputs_=dict(product=dict(path='product.json', sha256=True)))
        configs.append(OmegaConf.to_container(config, resolve=False))
    # Export a new queue once, rather than 1000 calls appending YAML.
    with Path(queue).open('x') as stream:
        yaml.safe_dump(configs, stream, sort_keys=False)


def check_coverage(manifest, root, *, check_current_inputs=False):
    rows = read_manifest(manifest)
    root = Path(root).resolve()
    expected = {row['item_id'] for row in rows if row['disposition'] == 'process'}
    observed = {p.name for p in (root / 'items').iterdir()
                if p.is_dir() and p.name != '.flexlock'} if (root / 'items').exists() else set()
    issues = [f'Unexpected item directory: {i}' for i in sorted(observed - expected)]
    summary = {'produced': [], 'empty': [], 'excluded': [], 'issues': issues}
    for row in rows:
        item = row['item_id']
        if row['disposition'] == 'excluded':
            summary['excluded'].append({'item_id': item, 'reason': row['reason']})
            continue
        directory = root / 'items' / item
        try:
            if not (directory / 'run.complete').is_file():
                raise ValueError('no completion marker')
            record = load_record(directory)
            if not record or record['config']['item_id'] != item:
                raise ValueError('missing/wrong invocation record')
            if Path(record['config']['input_path']).resolve() != Path(row['input_path']).resolve():
                raise ValueError('wrong input binding')
            if record['config'].get('expected_sha256') != row['sha256']:
                raise ValueError('recorded input identity differs from frozen manifest')
            product = directory / 'product.json'
            from flexlock.outputs import validate_outputs
            validate_outputs(OmegaConf.create(record['config']), record_dir=directory)
            payload = json.loads(product.read_text())
            if payload['item_id'] != item or payload['outcome'] not in ('produced', 'empty'):
                raise ValueError('wrong product identity/outcome')
            if payload['count'] < 0 or (payload['outcome'] == 'empty') != (payload['count'] == 0):
                raise ValueError('inconsistent coverage payload')
            if payload.get('input_sha256') != row['sha256']:
                raise ValueError('processed input identity differs from frozen manifest')
            if check_current_inputs and hashlib.sha256(Path(row['input_path']).read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('current input identity changed')
            summary[payload['outcome']].append(item)
        except (OSError, ValueError, KeyError, TypeError, FlexLockError) as exc:
            issues.append(f'{item}: {exc}')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export', 'check'])
    parser.add_argument('manifest'); parser.add_argument('root'); parser.add_argument('output')
    parser.add_argument('--check-current-inputs', action='store_true')
    args = parser.parse_args()
    if args.action == 'export':
        export_queue(args.manifest, args.root, args.output)
    else:
        summary = check_coverage(args.manifest, args.root, check_current_inputs=args.check_current_inputs)
        with Path(args.output).open('x') as stream:
            json.dump(summary, stream, indent=2)
        if summary['issues']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
