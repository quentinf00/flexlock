"""Isolated SAR coverage gate: exact queue evidence plus expected CSV presence.

Run after workers stop, before assembly. Files must not be moved/deleted between
extraction and checking. A present CSV needs separate scientific/reuse acceptance.
"""
import argparse
import json
from pathlib import Path

from flexlock.record import list_task_records


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
