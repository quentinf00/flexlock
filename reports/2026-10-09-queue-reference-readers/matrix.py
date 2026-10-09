"""Sequential fresh-process, alternating comparisons; keep source frozen."""
import argparse
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
    report = dict(revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  hostname=os.uname().nodename, runs=[])
    for rep in range(3):
        for fixture in ('prep', 'terminal', 'future'):
            for baseline in ([True, False] if rep % 2 == 0 else [False, True]):
                name = f'{fixture}-{rep}-'+('baseline' if baseline else 'current')
                driver = Path(__file__).with_name('prep.py' if fixture == 'prep' else 'cohort.py')
                command = [sys.executable, str(driver), '--output', str(root/name)]
                if fixture == 'prep':
                    command.extend(['--inputs', args.inputs])
                elif fixture == 'future':
                    command.append('--future')
                if baseline:
                    command.append('--baseline')
                print(json.dumps(dict(event='start', case=name)), flush=True)
                with (root/f'{name}.log').open('w') as log:
                    subprocess.run(command, env=dict(os.environ, FLEXLOCK_PREP_PROCESSES='1'),
                                   stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
                result = json.loads((root/name/'measurement.json').read_text())
                report['runs'].append(dict(case=name, **result))
                (root/'results.json').write_text(json.dumps(report, indent=2)+'\n')
                print(json.dumps(dict(event='finish', case=name, seconds=result['seconds'])), flush=True)


if __name__ == '__main__':
    main()
