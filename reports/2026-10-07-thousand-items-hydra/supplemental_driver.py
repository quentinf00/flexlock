import json, os, subprocess, sys, time
from pathlib import Path
root=Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/supplement')
root.mkdir(exist_ok=False)
inputs='/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs'
cases=[
 ('identity','identity',1000,[],inputs),
 ('tracked-local','flexlock-local',1000,['--provenance','--data'],inputs),
 ('source-submit','flexlock-slurm',1000,['--provenance'],inputs),
 ('cache-miss-submit','flexlock-slurm',1000,['--cache-search'],inputs),
 ('batch16-local','flexlock-local',1000,['--batch','16'],inputs),
 ('db-submit','flexlock-slurm',1000,['--record','db'],inputs),
 ('tmp-queue1','queue',1000,[],'/tmp/flexlock-hydra-benchmark/inputs'),
 ('tmp-queue16','queue',1000,['--batch','16'],'/tmp/flexlock-hydra-benchmark/inputs'),
 ('profile-flexlock-local','flexlock-local',100,['--profile'],inputs),
 ('profile-flexlock-submit','flexlock-slurm',100,['--profile'],inputs),
 ('profile-hydra-local','hydra-local',100,['--profile'],inputs),
]
m=dict(hostname=os.uname().nodename,source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),runs=[])
for label,kind,n,extras,fixture in cases:
 output=(Path('/tmp/flexlock-hydra-benchmark')/label) if label.startswith('tmp-') else root/label
 command=[sys.executable,'-m','benchmarks.thousand_items.measure','--kind',kind,'--count',str(n),'--output',str(output),'--inputs',fixture,*extras]
 entry=dict(variant=label,count=n,repeat=0,command=command,start=time.time(),loadavg=os.getloadavg())
 print(json.dumps(dict(event='start',variant=label)),flush=True)
 start=time.perf_counter()
 try:
  c=subprocess.run(command,capture_output=True,text=True,timeout=1200)
  entry.update(exit_code=c.returncode,stdout=c.stdout,stderr=c.stderr)
 except subprocess.TimeoutExpired as e:entry.update(exit_code=124,stderr=str(e.stderr),stdout=str(e.stdout))
 entry['process_seconds']=time.perf_counter()-start
 if (output/'measurement.json').exists():entry['measurement']=json.loads((output/'measurement.json').read_text())
 m['runs'].append(entry)
 (root/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
 print(json.dumps(dict(event='finish',variant=label,exit_code=entry['exit_code'],seconds=entry.get('measurement',{}).get('seconds'))),flush=True)
raise SystemExit(any(r['exit_code'] for r in m['runs']))
