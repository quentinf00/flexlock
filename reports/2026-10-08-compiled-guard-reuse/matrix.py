"""Sequential rotating baseline/candidate comparisons in fresh processes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--inputs', required=True)
    args = parser.parse_args()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    driver = Path(__file__).with_name('case.py')
    report = dict(revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  hostname=os.uname().nodename, affinity_cpus=len(os.sched_getaffinity(0)),
                  driver_sha256=hashlib.sha256(driver.read_bytes()).hexdigest(), runs=[])
    cases = []
    for rep in range(3):
        for fixture in ['plain', 'producer']:
            order = [True, False] if rep % 2 == 0 else [False, True]
            for baseline in order:
                name = f'{fixture}-{rep}-'+('baseline' if baseline else 'reuse')
                extra = ['--producer'] if fixture == 'producer' else []
                cases.append((name, baseline, extra))
    cases.extend([('small-baseline', True, ['--count', '100']),
                  ('small-reuse', False, ['--count', '100']),
                  ('local-100', False, ['--count', '100', '--local']),
                  ('source-baseline', True, ['--provenance']),
                  ('source-reuse', False, ['--provenance'])])
    for name, baseline, extra in cases:
        command = [sys.executable, str(driver), '--output', str(root/name), '--inputs', args.inputs, *extra]
        if baseline:
            command.append('--baseline')
        print(json.dumps(dict(event='start', case=name)), flush=True)
        with (root/f'{name}.log').open('w') as log:
            subprocess.run(command, env=dict(os.environ, FLEXLOCK_PREP_PROCESSES='1'),
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        result = json.loads((root/name/'measurement.json').read_text())
        report['runs'].append(dict(case=name, **result))
        (root/'results.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(dict(event='finish', case=name, seconds=result['seconds'],
                              **result['guard_reuse'])), flush=True)


if __name__ == '__main__':
    main()
