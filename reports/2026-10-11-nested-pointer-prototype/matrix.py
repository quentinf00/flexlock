"""Bounded format experiment before requesting a reader-compatibility decision."""
import json
import os
from pathlib import Path
import subprocess
import sys
root = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-11-pointer-experiment')
root.mkdir(parents=True, exist_ok=False)
result = dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              hostname=os.uname().nodename, runs=[])
for rep in range(3):
    for omit in ([False,True] if rep%2 == 0 else [True,False]):
        name = f'{rep}-'+('omit' if omit else 'current')
        command=[sys.executable,str(Path(__file__).with_name('case.py')),'--data','--output',str(root/name),
                 '--inputs','/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs']
        if omit:command.append('--omit-nested-pointers')
        print(json.dumps(dict(event='start',case=name)),flush=True)
        with (root/(name+'.log')).open('w') as log:
            subprocess.run(command,env=dict(os.environ,FLEXLOCK_PREP_PROCESSES='1'),stdout=log,
                           stderr=subprocess.STDOUT,check=True,timeout=300)
        row=json.loads((root/name/'measurement.json').read_text())
        result['runs'].append(dict(case=name,omit=omit,**row))
        (root/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(event='finish',case=name,seconds=row['seconds'],files=row['artifact_files'])),flush=True)
