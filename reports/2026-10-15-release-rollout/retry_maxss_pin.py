from pathlib import Path
import json,re,subprocess,os,importlib.metadata
import yaml
r=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout');wheel=str(r/'flexlock-0.9.3-py3-none-any.whl');oldwheel=str(r.parent/'2026-10-12-pandas-removal/flexlock-0.9.2-py3-none-any.whl');base=Path('/scale/scratch/qfebvre/flexlock093-rollout-preserved/maxss-retry');base.mkdir(exist_ok=False)
queue=subprocess.check_output(['squeue','-u','qfebvre','-o','%i %T %j %Z'],text=True);assert 'maxss' not in queue.lower() and '1370177' not in queue
(r/'jobs-before-maxss-retry.txt').write_text(queue)
plans=[x for x in json.loads((r/'pin-plan.json').read_text()) if x['defer']];assert len(plans)==3;results=[]
for index,row in enumerate(plans):
 root=Path(row['root']);manifest=Path(row['manifest']);lock=Path(row['lock']);before=manifest.read_text();old=lock.read_text();new=before.replace(oldwheel,wheel);candidate=old.replace(oldwheel,wheel);marker='- pypi: '+wheel+'\n  name: flexlock\n  version: 0.9.2';assert candidate.count(marker)==1;candidate=candidate.replace(marker,marker[:-5]+'0.9.3');assert new!=before
 backup=base/str(index);backup.mkdir();(backup/manifest.name).write_text(before);(backup/'pixi.lock').write_text(old)
 a=yaml.safe_load(old);b=yaml.safe_load(candidate)
 for pkg in b['packages']:
  if pkg.get('name')=='flexlock':pkg['pypi']=oldwheel;pkg['version']='0.9.2'
 def replace(v):
  if isinstance(v,str):return v.replace(wheel,oldwheel)
  if isinstance(v,list):return [replace(x) for x in v]
  if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
  return v
 assert a==replace(b)
 assert manifest.read_text()==before and lock.read_text()==old
 manifest.write_text(new);lock.write_text(candidate)
 with (r/f'maxss-retry-{index}.pin-check.log').open('w') as stream:
  p=subprocess.run(['/ontap/user/qfebvre/.pixi/bin/pixi','lock','--check','--no-install','--manifest-path',str(manifest)],stdout=stream,stderr=subprocess.STDOUT,timeout=60)
 assert p.returncode==0 and manifest.read_text()==new and lock.read_text()==candidate,'Inspect state; preserve concurrent changes'
 proposed=backup/'proposed';proposed.mkdir();(proposed/manifest.name).write_text(new);(proposed/'pixi.lock').write_text(candidate)
 result=dict(root=str(root),manifest=str(manifest),backup=str(backup),proposed=str(proposed),status='pinned',pixi_check_exit=0,non_flexlock_lock_unchanged=True);results.append(result);(r/'maxss-pin-retry.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(result),flush=True)
rows=json.loads((r/'prefix-preflight.json').read_text());env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');env.pop('PYTHONPATH',None)
for row in rows:
 if not row['defer']:continue
 probe=subprocess.check_output([row['prefix']+'/bin/python','-c',"import importlib.metadata as m,json,sysconfig; d=m.distribution('flexlock'); print(json.dumps(dict(version=d.version,requires=d.requires,site=sysconfig.get_paths()['purelib'])))"],cwd='/tmp',env=env,text=True)
 data=json.loads(probe);assert data['version']=='0.9.2';row.update(probe=data,site=data['site'],eligible=True,defer=False,reason='MaxSS job 1370177 completed; scheduler rechecked idle')
(r/'maxss-prefix-preflight.json').write_text(json.dumps(rows,indent=2)+'\n')
