import json,os,hashlib,subprocess,tarfile,re
from pathlib import Path
r=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout');rows=json.loads((r/'prefix-preflight.json').read_text());wheel=r/'flexlock-0.9.3-py3-none-any.whl';backup_root=Path('/scale/scratch/qfebvre/flexlock093-rollout-preserved/prefix-backups')
assert re.search(r'^1053 passed, 2 skipped, 1 xfailed',(r/'full-suite-release.log').read_text(),re.M)
identity=json.loads((r/'wheel-identity.json').read_text());assert hashlib.sha256(wheel.read_bytes()).hexdigest()==identity['sha256']
requirements={x.removeprefix('Requires-Dist: ') for x in identity['metadata'].splitlines() if x.startswith('Requires-Dist: ')}
backup_root.mkdir(exist_ok=True);env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1');env.pop('PYTHONPATH',None)
probe='''import json,tempfile
from pathlib import Path
import flexlock
from flexlock.run_record import RunRecord
from flexlock.record import load_record
from flexlock.taskdb import queue_tasks
from flexlock.destination_guard import reserve_queue,has_active_destination
assert flexlock.__version__=='0.9.3'
assert '/site-packages/flexlock/' in flexlock.__file__
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);d=root/'run';d.mkdir();r=RunRecord(d)
 r.write_lock({'config':{'save_dir':str(d)}})
 (d/'results.json').write_text('{"science":17}')
 r.write_results({'return':42});r.mark_complete()
 assert json.loads((d/'results.json').read_text())=={'science':17}
 assert load_record(d)['result']=={'return':42} and r.load_results()=={'return':42}
 old=root/'legacy';old.mkdir();(old/'run.lock').write_text('config: {}\\n');(old/'results.json').write_text('{"old":42}')
 assert RunRecord(old).load_results()=={'old':42}
 product=root/'queue/item';db=root/'queue/run.lock.tasks.db'
 queue_tasks(db,[dict(save_dir=str(product))]);reserve_queue([product],db)
 assert not (product/'.flexlock-queue.json').exists() and has_active_destination(product)
print(json.dumps(dict(version=flexlock.__version__,source=flexlock.__file__,record_results=True,legacy_read=True,queue_guard=True)))
'''
results=[]
for row in rows:
 prefix=Path(row['prefix']);site=Path(row['site'])
 # Defer all stale Biomass aliases, SOBA and the old template while their
 # manifest validation is blocked by missing sources/unsatisfiable constraints.
 blocked=(prefix.parent.parent.name.startswith(('biomass-proc-','biomass_proc-','biomass_pipeline-','soba-bench-','myproject-')))
 if row['defer'] or blocked:
  results.append(dict(prefix=str(prefix),status='deferred',reason=row['reason'] if row['defer'] else 'project pin validation failed; manifest/lock restored'))
  continue
 assert row.get('eligible'),row
 assert set(row['probe']['requires'])==requirements,(prefix,'dependency requirement change')
 key=hashlib.sha256(str(prefix).encode()).hexdigest()[:16];archive=backup_root/(key+'.tar.gz');assert not archive.exists(),archive
 paths=set(site.glob('flexlock*'))|set(site.glob('*flexlock*.pth'))
 paths.update(p for p in (prefix/'bin').glob('flexlock*') if p.is_file())
 assert paths
 with tarfile.open(archive,'w:gz') as tar:
  for path in sorted(paths):tar.add(path,arcname=str(path.relative_to(prefix)))
 before=sorted(p.name for p in site.glob('*.dist-info') if not p.name.lower().startswith('flexlock-'))
 log=r/(key+'.install.log')
 with log.open('w') as stream:
  process=subprocess.run(['/ontap/user/qfebvre/.local/bin/uv','pip','install','--offline','--no-deps','--reinstall-package','flexlock','--python',str(prefix/'bin/python'),str(wheel)],cwd='/tmp',env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
 result=dict(prefix=str(prefix),backup=str(archive),install_exit=process.returncode,status='installed' if process.returncode==0 else 'failed')
 if process.returncode==0:
  after=sorted(p.name for p in site.glob('*.dist-info') if not p.name.lower().startswith('flexlock-'));assert before==after,(prefix,'unrelated distribution change')
  check=subprocess.run([str(prefix/'bin/python'),'-c',probe],cwd='/tmp',env=env,text=True,capture_output=True,timeout=60)
  result.update(probe_exit=check.returncode,probe_output=check.stdout,probe_error=check.stderr,other_distribution_names_unchanged=True)
  if check.returncode:result['status']='probe-failed'
 results.append(result);(r/'installation-results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(result),flush=True)
 if result['status']!='installed':raise RuntimeError('Stop and inspect failed installation '+str(prefix))
(r/'installation-results.json').write_text(json.dumps(results,indent=2)+'\n')
print('Installed',sum(x['status']=='installed' for x in results),'deferred',sum(x['status']=='deferred' for x in results),flush=True)
