"""Frozen sequential plain/producer controls and phase measurements."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-10-preparation-phases')
root.mkdir(parents=True, exist_ok=False)
report = dict(revision=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
              hostname=os.uname().nodename, runs=[])
for rep in range(4):
    for fixture in ('plain', 'producer'):
        instrumented = rep != 0
        name=f'{fixture}-'+('control' if not instrumented else str(rep))
        driver=(Path(__file__).with_name('case.py') if instrumented else Path(__file__).resolve().parents[1]/'2026-10-08-process-preparation'/'case.py')
        command=[sys.executable,str(driver),'--output',str(root/name),
                 '--inputs','/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs']
        if instrumented:command.append('--instrument')
        if fixture == 'producer':command.append('--producer')
        print(json.dumps(dict(event='start',case=name)),flush=True)
        with (root/(name+'.log')).open('w') as log:
            subprocess.run(command, env=dict(os.environ,FLEXLOCK_PREP_PROCESSES='1'),
                           stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        row=json.loads((root/name/'measurement.json').read_text())
        row['instrumented']=instrumented
        row['timings']=json.loads((root/name/'phase-timings.json').read_text()) if instrumented else {}
        report['runs'].append(dict(case=name,**row))
        (root/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(event='finish',case=name,seconds=row['seconds'])),flush=True)
