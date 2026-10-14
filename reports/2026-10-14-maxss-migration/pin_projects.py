import json,subprocess,sys,hashlib
from pathlib import Path
import yaml
from urllib.parse import urlparse,unquote
REPORT=Path(__file__).resolve().parent
ALLOWED={'flexlock','gitpython','gitdb','smmap','loguru','xxhash','joblib','omegaconf','antlr4-python3-runtime','cloudpickle','pyyaml','python-xxhash','antlr-python-runtime','libyaml','tcwind-benchtools','zarrpatch'}
def identities(raw):
 result={}
 for pkg in (yaml.safe_load(raw) or {}).get('packages',[]):
  name=pkg.get('name');source=pkg.get('conda',pkg.get('pypi'))
  if not name and pkg.get('conda'):
   file=unquote(Path(urlparse(source).path).name)
   for suffix in ['.tar.bz2','.conda']:
    if file.endswith(suffix):file=file[:-len(suffix)];break
   name=file.rsplit('-',2)[0]
  if not name:raise ValueError('Unknown package identity '+str(pkg))
  result.setdefault(name.lower().replace('_','-'),set()).add(source)
 return result
rows=json.loads((REPORT/'pin-plan.json').read_text())
if len(sys.argv)>1:rows=[r for r in rows if sys.argv[1] in r['manifest']]
if (REPORT/'pin-results.json').exists():
 completed={r['manifest'] for r in json.loads((REPORT/'pin-results.json').read_text())}
 rows=[r for r in rows if r['manifest'] not in completed]
results=[]
for row in rows:
 manifest=Path(row['manifest']);lock=Path(row['lock']);proposed=Path(row['proposed'])
 backup=REPORT/'pins-before'/str(manifest.parent.relative_to('/ontap/user/qfebvre'))
 backup.mkdir(parents=True,exist_ok=True)
 raw=manifest.read_bytes();old_lock=lock.read_bytes() if lock.exists() else None
 if (backup/manifest.name).exists():raise RuntimeError('Existing pin backup; inspect before retrying '+str(manifest))
 (backup/manifest.name).write_bytes(raw)
 if old_lock is not None:(backup/'pixi.lock').write_bytes(old_lock)
 manifest.write_bytes(proposed.read_bytes())
 identity=hashlib.sha256(str(manifest).encode()).hexdigest()[:16]
 log=REPORT/(identity+'.pin.log')
 result=dict(manifest=str(manifest),lock=str(lock))
 try:
  with log.open('w') as output:
   process=subprocess.run(['/ontap/user/qfebvre/.pixi/bin/pixi','lock','--no-install','--manifest-path',str(manifest)],stdout=output,stderr=subprocess.STDOUT,timeout=75)
  if process.returncode:raise RuntimeError('Pixi lock failed; see '+str(log))
  changes=[]
  if old_lock:
   old,new=identities(old_lock),identities(lock.read_bytes())
   changes=[name for name in old.keys()|new.keys() if old.get(name)!=new.get(name)]
   if set(changes)-ALLOWED:raise RuntimeError('Unrelated locked package changes: '+str(sorted(set(changes)-ALLOWED)))
  result.update(status='pinned',changed_packages=sorted(changes))
 except Exception as exc:
  manifest.write_bytes(raw)
  if old_lock is not None:lock.write_bytes(old_lock)
  elif lock.exists():lock.unlink()
  result.update(status='restored',reason=str(exc))
 results.append(result)
 path=REPORT/'pin-results.json'
 existing=json.loads(path.read_text()) if path.exists() else []
 path.write_text(json.dumps(existing+[result],indent=2)+'\n')
 print(json.dumps(result),flush=True)
