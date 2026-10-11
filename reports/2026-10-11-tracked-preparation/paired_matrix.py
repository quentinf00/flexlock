"""Three alternating pairs, each with source and per-item data enabled."""
import json
import os
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
root = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-11-source-grouping-isolated')
root.mkdir(parents=True, exist_ok=False)
result = dict(revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              hostname=os.uname().nodename, runs=[])
for rep in range(3):
    for baseline in ([True, False] if rep % 2 == 0 else [False, True]):
        name = f'{rep}-'+('baseline' if baseline else 'current')
        command = [sys.executable, str(here/'paired.py'), '--data', '--output', str(root/name),
                   '--inputs', '/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs']
        if baseline:
            command.append('--baseline')
        print(json.dumps(dict(event='start', case=name)), flush=True)
        with (root/(name+'.log')).open('w') as log:
            subprocess.run(command, env=dict(os.environ, FLEXLOCK_PREP_PROCESSES='1'),
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        row = json.loads((root/name/'measurement.json').read_text())
        result['runs'].append(dict(case=name, baseline=baseline, **row))
        (root/'results.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(dict(event='finish', case=name, seconds=row['seconds'],
                              collection=row['repo_collection'])), flush=True)
