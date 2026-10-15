from pathlib import Path
import json,re,tarfile,hashlib,subprocess,os
r=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout');installs=json.loads((r/'installation-results.json').read_text());pre={x['prefix']:x for x in json.loads((r/'prefix-preflight.json').read_text())};checks=[]
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');env.pop('PYTHONPATH',None)
for x in installs:
 expected='0.9.3' if x['status']=='installed' else '0.9.2'
 row=pre[x['prefix']]
 if x['status']=='deferred':
  site=subprocess.check_output([x['prefix']+'/bin/python','-c',"import sysconfig; print(sysconfig.get_paths()['purelib'])"],cwd='/tmp',env=env,text=True).strip();row['site']=site
 p=Path(row['site'])/'flexlock/__init__.py';version=re.search(r'__version__ = [\"\']([^\"\']+)',p.read_text())[1]
 assert version==expected,(x['prefix'],version,expected)
 item=dict(prefix=x['prefix'],source=str(p),version=version,status=x['status'])
 if x['status']=='installed':
  archive=Path(x['backup']);assert archive.exists()
  with tarfile.open(archive) as tar:
   entry=next(m for m in tar.getmembers() if m.name.endswith('/flexlock/__init__.py'))
   assert b'__version__ = "0.9.2"' in tar.extractfile(entry).read()
  item['backup_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
 checks.append(item)
(r/'prefix-preflight.json').write_text(json.dumps(list(pre.values()),indent=2)+'\n')
(r/'final-version-audit.json').write_text(json.dumps(checks,indent=2)+'\n')
print('Verified',len(checks),'prefix versions and all installed-prefix old-version backups')
updates=json.loads((r/'guidance-updates.json').read_text());assert len(updates)==21 and sum(x['agents_updated'] for x in updates)==19
for x in updates:
 assert Path(x['feedback']).exists()
 if x['agents_updated']:assert '## FlexLock release compatibility (2026-10-15; 0.9.3)' in (Path(x['root'])/'AGENTS.md').read_text()
print('Verified 21 feedback files and 19 compatibility updates')

plans={x['root']:x for x in json.loads((r/'pin-plan.json').read_text())};pins=[]
for row in json.loads((r/'pin-results.json').read_text()):
 root=Path(row['root']);item=dict(root=str(root),status=row['status'])
 if row['status']=='pinned':
  candidate=Path(plans[str(root)]['proposed']);manifest=Path(row['manifest']).name
  item.update(manifest_matches=(root/manifest).read_bytes()==(candidate/manifest).read_bytes(),lock_matches=(root/'pixi.lock').read_bytes()==(candidate/'pixi.lock').read_bytes())
  assert item['manifest_matches'] and item['lock_matches'],item
 else:item['deferred']=True
 pins.append(item)
(r/'final-pin-audit.json').write_text(json.dumps(pins,indent=2)+'\n')
assert sum(x['status']=='pinned' for x in pins)==19
import zipfile
wheel=r/'flexlock-0.9.3-py3-none-any.whl';identity=json.loads((r/'wheel-identity.json').read_text());assert hashlib.sha256(wheel.read_bytes()).hexdigest()==identity['sha256']
with zipfile.ZipFile(wheel) as archive:
 for name in archive.namelist():
  if name.startswith('flexlock/') and name.endswith('.py'):assert archive.read(name)==(r.parent.parent/name).read_bytes(),name
print('Verified 19 project pins, wheel hash and matching Python sources')
