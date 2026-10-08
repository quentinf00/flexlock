"""Sequential, rotating fresh-process trials; source must remain frozen."""
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
    case_driver = Path(__file__).with_name('case.py')
    report = dict(revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  hostname=os.uname().nodename, affinity_cpus=len(os.sched_getaffinity(0)),
                  case_sha256=hashlib.sha256(case_driver.read_bytes()).hexdigest(), runs=[])
    cases = []
    for rep in range(3):
        order = [1, 2, 4]
        order = order[rep:] + order[:rep]
        for fixture in ['plain', 'producer']:
            for workers in order:
                cases.append((f'{fixture}-{rep}-{workers}', workers, ['--producer'] if fixture == 'producer' else []))
    cases.extend([('small-serial', 1, ['--count', '100']), ('small-optin', 4, ['--count', '100']),
                  ('local-100', 2, ['--count', '100', '--local']),
                  ('source-1000', 2, ['--provenance'])])
    for name, workers, extra in cases:
        env = dict(os.environ, FLEXLOCK_PREP_PROCESSES=str(workers))
        command = [sys.executable, str(case_driver), '--output', str(root/name), '--inputs', args.inputs, *extra]
        print(json.dumps(dict(event='start', case=name)), flush=True)
        with (root/f'{name}.log').open('w') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        result = json.loads((root/name/'measurement.json').read_text())
        report['runs'].append(dict(case=name, requested_workers=workers, **result))
        (root/'results.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(dict(event='finish', case=name, seconds=result['seconds'], **result['compilation'])), flush=True)


if __name__ == '__main__':
    main()
