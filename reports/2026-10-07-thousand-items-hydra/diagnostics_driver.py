import json, os, subprocess, sys, time
from pathlib import Path
root=Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/supplement')
cases=[('profile-tracked-local','flexlock-local',100,['--provenance','--data','--profile'],{}),
 ('cache-index-only-submit','flexlock-slurm',1000,['--cache-search'],{'FLEXLOCK_INDEX_FALLBACK':'0'}),
 ('profile-cache-submit','flexlock-slurm',100,['--cache-search','--profile'],{})]
for label,kind,n,flags,overrides in cases:
 output=root/label
 command=[sys.executable,'-m','benchmarks.thousand_items.measure','--kind',kind,'--count',str(n),'--output',str(output),'--inputs','/ontap/user/qfebvre/flexlock-hydra-benchmark/inputs',*flags]
 entry=dict(variant=label,count=n,repeat=0,command=command,environment_overrides=overrides,start=time.time(),loadavg=os.getloadavg())
 print(json.dumps(dict(event='start',variant=label)),flush=True)
 start=time.perf_counter();c=subprocess.run(command,capture_output=True,text=True,timeout=900,env={**os.environ,**overrides})
 entry.update(exit_code=c.returncode,stdout=c.stdout,stderr=c.stderr,process_seconds=time.perf_counter()-start)
 if (output/'measurement.json').exists():entry['measurement']=json.loads((output/'measurement.json').read_text())
 p=root/'manifest.json';m=json.loads(p.read_text());m['runs'].append(entry);p.write_text(json.dumps(m,indent=2)+'\n')
 print(json.dumps(dict(event='finish',variant=label,exit_code=c.returncode,seconds=entry.get('measurement',{}).get('seconds'))),flush=True)
 if c.returncode:raise SystemExit(c.returncode)
