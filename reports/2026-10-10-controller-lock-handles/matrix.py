"""Fresh processes, sequential alternating full-preparation pairs."""
import json,os,subprocess,sys
from pathlib import Path
root=Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-10-controller-lock-handles')
root.mkdir(parents=True,exist_ok=False)
report=dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),hostname=os.uname().nodename,runs=[])
for rep in range(3):
    for fixture in ('plain','producer'):
        for baseline in ([True,False] if rep % 2 == 0 else [False,True]):
            name=f'{fixture}-{rep}-'+('baseline' if baseline else 'current')
            command=[sys.executable,str(Path(__file__).with_name('prep.py')),'--output',str(root/name),'--inputs','/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs']
            if fixture == 'producer':command.append('--producer')
            if baseline:command.append('--baseline')
            print(json.dumps(dict(event='start',case=name)),flush=True)
            with (root/(name+'.log')).open('w') as log:
                subprocess.run(command,env=dict(os.environ,FLEXLOCK_PREP_PROCESSES='1'),stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
            row=json.loads((root/name/'measurement.json').read_text())
            report['runs'].append(dict(case=name,**row))
            (root/'results.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(dict(event='finish',case=name,seconds=row['seconds'],guard=row['guard'])),flush=True)
