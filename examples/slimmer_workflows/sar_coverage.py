"""Isolated SAR coverage gate: exact queue evidence plus expected CSV presence.

Run after workers stop, before assembly. Files must not be moved/deleted between
extraction and checking. A present CSV needs separate scientific/reuse acceptance.
Scientific errors must propagate. Current SAR helpers suppress some errors;
real adoption needs strict handling or explicit partial-error accounting first.
"""
import argparse
import json
from pathlib import Path

from flexlock.record import list_task_records


def bind_membership(database, expected_items, extractor_target, output):
    """Bind already frozen process membership to queue IDs before execution.

    expected_items contains safe/save_dir pairs; queue membership never defines
    the expected cohort. Refuse missing/ambiguous matches and write exclusively.
    """
    database = Path(database)
    if not database.is_absolute() or not database.is_file():
        raise ValueError('Existing absolute authoritative database required')
    expected_items = list(expected_items)
    if len({item['safe'] for item in expected_items}) != len(expected_items):
        raise ValueError('Duplicate frozen SAFE membership')
    rows = list_task_records(database)
    by_binding = {}
    for row in rows:
        cfg = row.get('config', {})
        key = (cfg.get('_target_'), cfg.get('safe'), cfg.get('save_dir'))
        by_binding.setdefault(key, []).append(row['task_id'])
    items = []
    for item in expected_items:
        safe, directory = item['safe'], item['save_dir']
        if not Path(safe).is_absolute() or not Path(directory).is_absolute():
            raise ValueError('Frozen SAFE and destination paths must be absolute')
        matches = by_binding.get((extractor_target, safe, directory), [])
        if len(matches) != 1:
            raise ValueError(f'{safe}: expected exactly one matching queued invocation')
        items.append(dict(safe=safe, save_dir=directory, task_id=matches[0]))
    manifest = dict(database=str(database), extractor_target=extractor_target, items=items)
    with Path(output).open('x') as stream:
        json.dump(manifest, stream, indent=2)
    return manifest


def check_coverage(manifest):
    """Manifest: database, extractor_target, items with safe/task_id/save_dir."""
    database = Path(manifest['database'])
    if not database.is_absolute():
        raise ValueError('Use an absolute authoritative queue database path')
    items = manifest['items']
    ids = [item['task_id'] for item in items]
    safes = [item['safe'] for item in items]
    if len(set(ids)) != len(ids) or len(set(safes)) != len(safes):
        raise ValueError('Duplicate task IDs or SAFE membership')
    report = dict(present=[], empty=[], issues=[], ready=False)
    if not database.is_file():
        report['issues'].append('Authoritative queue database is missing')
        return report
    # One queue read rather than one query/parse per SAFE.
    records = {row['task_id']: row for row in list_task_records(database)}
    for item in items:
        safe = item['safe']
        directory = Path(item['save_dir'])
        if not Path(safe).is_absolute() or not directory.is_absolute():
            raise ValueError('SAFE and destination paths must be absolute')
        row = records.get(item['task_id'])
        cfg = row.get('config', {}) if row else {}
        if not row:
            report['issues'].append(f'{safe}: missing queue task')
        elif (cfg.get('safe') != safe or cfg.get('_target_') != manifest['extractor_target']
              or cfg.get('save_dir') != str(directory)):
            report['issues'].append(f'{safe}: invocation differs from frozen selection')
        elif row['status'] != 'done':
            report['issues'].append(f"{safe}: task is {row['status']}")
        else:
            csv = directory / 'feats' / (Path(safe).stem + '_features.csv')
            if csv.is_file():
                report['present'].append(dict(safe=safe, csv=str(csv)))
            elif csv.exists() or csv.is_symlink():
                report['issues'].append(f'{safe}: expected CSV is not a regular file')
            else:
                report['empty'].append(safe)
    if not report['issues'] and not report['present']:
        report['issues'].append('No feature CSVs to assemble (empty cohort)')
    report['ready'] = not report['issues']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('report')
    args = parser.parse_args()
    report = check_coverage(json.loads(Path(args.manifest).read_text()))
    with Path(args.report).open('x') as stream:
        json.dump(report, stream, indent=2)
    if not report['ready']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
