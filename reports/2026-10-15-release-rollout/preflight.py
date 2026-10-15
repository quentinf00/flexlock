import os,json,subprocess
from pathlib import Path
r=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout')
rows=json.loads((r/'prefix-plan.json').read_text());results=[]
code="import sys,sysconfig,json,importlib.metadata as m; import flexlock; print(json.dumps(dict(prefix=sys.prefix,site=sysconfig.get_paths()['purelib'],version=flexlock.__version__,source=flexlock.__file__,requires=m.requires('flexlock'))))"
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1');env.pop('PYTHONPATH',None)
for row in rows:
 if row['defer']:results.append(row);continue
 p=subprocess.run([row['prefix']+'/bin/python','-c',code],cwd='/tmp',env=env,text=True,capture_output=True,timeout=45)
 if p.returncode:row.update(eligible=False,reason=p.stderr[-1200:])
 else:
  data=json.loads(p.stdout);row.update(probe=data,site=data['site'],eligible=Path(data['prefix']).resolve()==Path(row['prefix']).resolve() and data['version']=='0.9.2' and '/site-packages/flexlock/' in data['source'])
 results.append(row);(r/'prefix-preflight.json').write_text(json.dumps(results,indent=2)+'\n')
 print(Path(row['prefix']).parts[-3:],row.get('eligible'),flush=True)
(r/'prefix-preflight.json').write_text(json.dumps(results,indent=2)+'\n')
