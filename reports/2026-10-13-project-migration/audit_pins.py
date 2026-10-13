import json,yaml
from pathlib import Path
from urllib.parse import urlparse,unquote
REPORT=Path(__file__).resolve().parent
ALLOWED={'flexlock','gitpython','gitdb','smmap','loguru','xxhash','python-xxhash','joblib','omegaconf','antlr4-python3-runtime','antlr-python-runtime','cloudpickle','pyyaml','libyaml'}
def identities(raw):
 result={}
 for pkg in (yaml.safe_load(raw) or {}).get('packages',[]):
  name=pkg.get('name')
  source=pkg.get('conda',pkg.get('pypi'))
  if not name and pkg.get('conda'):
   file=unquote(Path(urlparse(source).path).name)
   for suffix in ['.tar.bz2','.conda']:
    if file.endswith(suffix):file=file[:-len(suffix)];break
   name=file.rsplit('-',2)[0]
  if not name:raise ValueError('Unknown package identity '+str(pkg))
  result.setdefault(name.lower().replace('_','-'),set()).add(source)
 return result
results=[]
for row in json.loads((REPORT/'pin-results.json').read_text()):
 if row['status']!='pinned':continue
 old=REPORT/'pins-before'/str(Path(row['manifest']).parent.relative_to('/ontap/user/qfebvre'))/'pixi.lock'
 if not old.exists():continue
 a,b=identities(old.read_bytes()),identities(Path(row['lock']).read_bytes())
 changes=sorted(n for n in a.keys()|b.keys() if a.get(n)!=b.get(n))
 result=dict(manifest=row['manifest'],changes=changes,unrelated=sorted(set(changes)-ALLOWED))
 results.append(result)
 print(json.dumps(result))
(REPORT/'artifact-audit.json').write_text(json.dumps(results,indent=2)+'\n')
