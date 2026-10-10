"""Additional prep pairs investigate the matrix slowdown; separate evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
root = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-10-destination-resolution')
rows = []
for rep in range(2):
    for baseline in ([False, True] if rep == 0 else [True, False]):
        variant = 'baseline' if baseline else 'current'
        output = root/f'prep-followup-{rep}-{variant}'
        command = [sys.executable, str(Path(__file__).with_name('prep.py')), '--output', str(output), '--inputs', '/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs']
        if baseline: command.append('--baseline')
        with (root/(output.name+'.log')).open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, FLEXLOCK_PREP_PROCESSES='1'), check=True, timeout=180)
        row = json.loads((output/'measurement.json').read_text())
        rows.append(dict(case=output.name, **row))
        (root/'prep-followup.json').write_text(json.dumps(rows, indent=2)+'\n')
        print(json.dumps(dict(case=output.name, seconds=row['seconds'])), flush=True)
