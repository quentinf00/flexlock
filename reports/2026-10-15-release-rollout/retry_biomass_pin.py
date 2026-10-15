from pathlib import Path
import json,re,hashlib,subprocess
import yaml
r=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout');root=Path('/scale/user/qfebvre/projects/260617_biomass/biomass_proc');manifest=root/'pyproject.toml';lock=root/'pixi.lock';oldwheel=str(r.parent/'2026-10-12-pandas-removal/flexlock-0.9.2-py3-none-any.whl');wheel=str(r/'flexlock-0.9.3-py3-none-any.whl')
before=manifest.read_text();old=lock.read_text();new=before.replace(oldwheel,wheel);candidate=old.replace(oldwheel,wheel);marker='- pypi: '+wheel+'\n  name: flexlock\n  version: 0.9.2';assert candidate.count(marker)==1;candidate=candidate.replace(marker,marker[:-5]+'0.9.3');assert new!=before
backup=Path('/scale/scratch/qfebvre/flexlock093-rollout-preserved/biomass-retry');backup.mkdir(exist_ok=False);(backup/'pyproject.toml').write_text(before);(backup/'pixi.lock').write_text(old)
assert manifest.read_text()==before and lock.read_text()==old
manifest.write_text(new);lock.write_text(candidate)
with (r/'biomass-retry.pin-check.log').open('w') as output:
 p=subprocess.run(['/ontap/user/qfebvre/.pixi/bin/pixi','lock','--check','--no-install','--manifest-path',str(manifest)],stdout=output,stderr=subprocess.STDOUT,timeout=60)
assert p.returncode==0,'Inspect project state; do not overwrite concurrent edits'
assert manifest.read_text()==new and lock.read_text()==candidate,'Concurrent change; preserve and review'
a=yaml.safe_load(old);b=yaml.safe_load(candidate)
for pkg in b['packages']:
 if pkg.get('name')=='flexlock':pkg['pypi']=oldwheel;pkg['version']='0.9.2'
def replace(v):
 if isinstance(v,str):return v.replace(wheel,oldwheel)
 if isinstance(v,list):return [replace(x) for x in v]
 if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
 return v
assert a==replace(b)
result=dict(root=str(root),manifest=str(manifest),backup=str(backup),status='pinned',pixi_check_exit=0,non_flexlock_lock_unchanged=True,project_dependency_repair_preserved=True)
(r/'biomass-pin-retry.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
