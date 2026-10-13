import json,re,tomllib
from pathlib import Path
REPORT=Path(__file__).resolve().parent
WHEEL=str(REPORT.parent/'2026-10-12-pandas-removal/flexlock-0.9.2-py3-none-any.whl')
rows=json.loads((REPORT.parent/'2026-10-12-reader-migration/installations-before.json').read_text())
roots={Path(r['site']).parents[5] for r in rows if '/work/projects/' in r['site'] and '/maxss-ml/' not in r['site'] and '/flexlock/.pixi/' not in r['site']}
roots.update([Path('/ontap/user/qfebvre/work/projects/2508_nextgems/nextgems_tc'),Path('/ontap/user/qfebvre/work/projects/260324_jepa/le-tc-wm')])
excluded={Path(r['site']).parents[5] for r in rows if 'maxss-ml-' in r['real_site'] and '/work/projects/' in r['site']}
excluded_inodes={(r.stat().st_dev,r.stat().st_ino) for r in excluded if r.exists()}
roots={r for r in roots if (r.stat().st_dev,r.stat().st_ino) not in excluded_inodes}
plans=[];skips=[];seen=set()
for root in sorted(roots):
 for fname in ['pixi.toml','pyproject.toml']:
  f=root/fname
  if not f.exists():continue
  identity=(f.stat().st_dev,f.stat().st_ino)
  if identity in seen:continue
  seen.add(identity)
  raw=f.read_text()
  if 'project_template' in str(f):
   pattern=r'(?ms)^\[tool\.pixi\.feature\.dev\.dependencies\]\n(.*?)(?=^\[|\Z)'
   blocks=list(re.finditer(pattern,raw))
   if len(blocks)==2:
    merged='[tool.pixi.feature.dev.dependencies]\n'+''.join(b.group(1) for b in blocks)
    raw=raw[:blocks[1].start()]+raw[blocks[1].end():]
    raw=raw[:blocks[0].start()]+merged+raw[blocks[0].end():]
  try:tomllib.loads(raw)
  except ValueError as exc:
   skips.append(dict(manifest=str(f),reason='Existing invalid TOML: '+str(exc)));continue
  section='';targets=set();out=[]
  for line in raw.splitlines(keepends=True):
   if line.strip().startswith('['):section=line.strip().strip('[]')
   if re.match(r'^\s*flexlock\s*=',line):
    if section.endswith('pypi-dependencies'):
     out.append('flexlock = { path = '+json.dumps(WHEEL)+' }\n');continue
    if section.endswith('dependencies'):
     targets.add(section[:-len('dependencies')]+'pypi-dependencies');continue
    raise ValueError((f,section))
   out.append(line)
  candidate=''.join(out)
  for table in sorted(targets):
   if '['+table+']' in candidate:
    candidate=candidate.replace('['+table+']','['+table+']\nflexlock = { path = '+json.dumps(WHEEL)+' }',1)
   else:candidate+='\n['+table+']\nflexlock = { path = '+json.dumps(WHEEL)+' }\n'
  if candidate==raw:continue
  tomllib.loads(candidate)
  stage=REPORT/'proposed'/str(root.relative_to('/ontap/user/qfebvre'))/fname
  stage.parent.mkdir(parents=True,exist_ok=True);stage.write_text(candidate)
  plans.append(dict(manifest=str(f),proposed=str(stage),lock=str(root/'pixi.lock')))
(REPORT/'pin-plan.json').write_text(json.dumps(plans,indent=2)+'\n')
(REPORT/'pin-skips.json').write_text(json.dumps(skips,indent=2)+'\n')
print('Prepared',len(plans),'distinct project manifest changes; skipped',len(skips))
for row in skips:print(row)
