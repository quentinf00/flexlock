"""Sequential fresh-process controls and nested phase diagnostics."""
import json
import os
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
root = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-11-tracked-preparation')
root.mkdir(parents=True, exist_ok=False)
result = dict(revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              hostname=os.uname().nodename, runs=[])
for rep in range(3):
    for data in (False, True):
        instrument = rep == 2
        name = ('source-data' if data else 'source')+f'-{rep}'
        command = [sys.executable]
        if instrument:
            command += [str(here.parent/'2026-10-10-preparation-phases'/'case.py'),
                        '--instrument', '--driver']
        command += [str(here/'case.py'), '--output', str(root/name), '--inputs',
                    '/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs']
        if data:
            command.append('--data')
        print(json.dumps(dict(event='start', case=name)), flush=True)
        with (root/(name+'.log')).open('w') as log:
            subprocess.run(command, env=dict(os.environ, FLEXLOCK_PREP_PROCESSES='1'),
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        row = json.loads((root/name/'measurement.json').read_text())
        result['runs'].append(dict(case=name, instrumented=instrument, **row))
        (root/'results.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(dict(event='finish', case=name, seconds=row['seconds'])), flush=True)
