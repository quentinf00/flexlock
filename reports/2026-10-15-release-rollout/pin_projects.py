import json,hashlib,subprocess,shutil,re,tomllib,copy
from pathlib import Path
import yaml
r=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout')
assert re.search(r'^1053 passed, 2 skipped, 1 xfailed', (r/'full-suite-release.log').read_text(), re.M),'Release tests must finish cleanly first'
plans=json.loads((r/'pin-plan.json').read_text());results=[]
def without_core(data):
 data=copy.deepcopy(data)
 core={p.get('conda',p.get('pypi')) for p in data['packages'] if p.get('name')=='flexlock' or 'flexlock-' in p.get('conda','')}
 data['packages']=[p for p in data['packages'] if p.get('conda',p.get('pypi')) not in core]
 for env in data['environments'].values():
  for platform,entries in env['packages'].items():env['packages'][platform]=[p for p in entries if p.get('conda',p.get('pypi')) not in core]
 return data
for row in plans:
 if row['defer']:
  results.append(dict(root=row['root'],status='deferred-active'));continue
 manifest=Path(row['manifest']);lock=Path(row['lock']);stage=Path(row['proposed']);identifier=hashlib.sha256(str(manifest).encode()).hexdigest()[:16];backup=r/'pins-before'/identifier
 assert not backup.exists(),backup
 before=manifest.read_bytes();old=lock.read_bytes();candidate=(stage/manifest.name).read_bytes();newlock=(stage/'pixi.lock').read_bytes()
 assert without_core(yaml.safe_load(old))==without_core(yaml.safe_load(newlock)),row['root']
 if row.get('old_wheel'):
  assert candidate.decode().replace(row['new_wheel'],row['old_wheel'])==before.decode(),'Concurrent manifest edit: '+str(manifest)
 tomllib.loads(candidate.decode());backup.mkdir(parents=True);(backup/manifest.name).write_bytes(before);(backup/'pixi.lock').write_bytes(old)
 manifest.write_bytes(candidate);lock.write_bytes(newlock)
 result=dict(root=row['root'],manifest=str(manifest),backup=str(backup),status='pinned',non_flexlock_lock_unchanged=True)
 try:
  with (r/(identifier+'.pin-check.log')).open('w') as output:
   check=subprocess.run(['/ontap/user/qfebvre/.pixi/bin/pixi','lock','--check','--no-install','--manifest-path',str(manifest)],stdout=output,stderr=subprocess.STDOUT,timeout=60)
  result['pixi_check_exit']=check.returncode
  # --check may write a proposed lock before returning non-zero. Keep exactly
  # the reviewed provider/version-only lock, not incidental resolver updates.
  observed=lock.read_bytes();result['pixi_check_changed_lock']=observed!=newlock
  if check.returncode or observed!=newlock:
   (r/(identifier+'.pixi-observed.lock')).write_bytes(observed)
   raise RuntimeError('Pixi check did not accept the reviewed lock unchanged')
 except Exception as exc:
  manifest.write_bytes(before);lock.write_bytes(old);result.update(status='restored-review-required',reason=str(exc))
 results.append(result);(r/'pin-results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(result),flush=True)
(r/'pin-results.json').write_text(json.dumps(results,indent=2)+'\n')
