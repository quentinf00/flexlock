from pathlib import Path
import json,yaml
from urllib.parse import urlparse,unquote
REPORT=Path(__file__).resolve().parent
ALLOWED={'flexlock','gitpython','gitdb','smmap','loguru','xxhash','python-xxhash','joblib','omegaconf','antlr4-python3-runtime','antlr-python-runtime','cloudpickle','pyyaml','libyaml','tcwind-benchtools','zarrpatch'}
def members(raw):
 data=yaml.safe_load(raw)
 names={}
 for pkg in data['packages']:
  source=pkg.get('conda',pkg.get('pypi'));name=pkg.get('name')
  if not name:
   file=unquote(Path(urlparse(source).path).name)
   for ext in ['.conda','.tar.bz2']:
    if file.endswith(ext):file=file[:-len(ext)];break
   name=file.rsplit('-',2)[0]
  names[source]=name.lower().replace('_','-')
 result={}
 for env,config in data['environments'].items():
  result[env]={}
  for platform,entries in config['packages'].items():
   for item in entries:
    source=item.get('conda',item.get('pypi'));name=names[source]
    result[env].setdefault(name,set()).add(source)
 return result
results=[]
for row in json.loads((REPORT/'pin-results.json').read_text()):
 if row['status']!='pinned':continue
 before=REPORT/'pins-before'/str(Path(row['manifest']).parent.relative_to('/ontap/user/qfebvre'))/'pixi.lock'
 if not before.exists():continue
 a,b=members(before.read_bytes()),members(Path(row['lock']).read_bytes());unexpected=[]
 for env in a.keys()|b.keys():
  old,new=a.get(env,{}),b.get(env,{})
  for name in old.keys()|new.keys():
   if old.get(name)!=new.get(name) and name not in ALLOWED:
    if name=='setuptools' and 'tmpl_smoke' in row['manifest'] and name not in new:continue
    unexpected.append(dict(environment=env,package=name,old=sorted(old.get(name,[])),new=sorted(new.get(name,[]))))
 results.append(dict(manifest=row['manifest'],unexpected=unexpected))
 print(row['manifest'],'unexpected',len(unexpected),flush=True)
(REPORT/'membership-audit.json').write_text(json.dumps(results,indent=2)+'\n')
assert all(not row['unexpected'] for row in results)
