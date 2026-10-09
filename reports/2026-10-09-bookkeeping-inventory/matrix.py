"""Six sequential fresh-process samples; frozen runtime and mocked scheduler."""
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
        for prototype in ([False, True] if rep % 2 == 0 else [True, False]):
            name = str(rep)+'-'+('omit' if prototype else 'current')
            command = [sys.executable, str(Path(__file__).with_name('case.py')),
                       '--output', str(root/name), '--inputs', args.inputs]
            if prototype:
                command.append('--omit-nested-pointers')
            print(json.dumps(dict(event='start', case=name)), flush=True)
            with (root/f'{name}.log').open('w') as log:
                subprocess.run(command, env=dict(os.environ, FLEXLOCK_PREP_PROCESSES='1'),
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
            result = json.loads((root/name/'measurement.json').read_text())
            report['runs'].append(dict(case=name, prototype=prototype, **result))
            (root/'results.json').write_text(json.dumps(report, indent=2)+'\n')
            print(json.dumps(dict(event='finish', case=name, seconds=result['seconds'],
                                  files=result['artifact_files'])), flush=True)


if __name__ == '__main__':
    main()
