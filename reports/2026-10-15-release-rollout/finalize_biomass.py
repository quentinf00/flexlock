from pathlib import Path
import json,re,hashlib,shutil
r=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout')
root=Path('/scale/user/qfebvre/projects/260617_biomass/biomass_proc')
def read(n):return json.loads((r/n).read_text())
def write(n,v): (r/n).write_text(json.dumps(v,indent=2)+'\n')
for name in ['installation-results.json','pin-results.json','pin-plan.json','guidance-updates.json']:
 backup=r/name.replace('.json','-initial.json')
 assert not backup.exists();shutil.copyfile(r/name,backup)
retry=read('biomass-installation-results.json');assert len(retry)==4 and all(x['status']=='installed' for x in retry)
by={x['prefix']:x for x in retry};write('installation-results.json',[by.get(x['prefix'],x) for x in read('installation-results.json')])
pins=read('pin-results.json');updated=read('biomass-pin-retry.json')
for i,x in enumerate(pins):
 if x['root']==str(root):pins[i]=updated
write('pin-results.json',pins)
proposal=Path(updated['backup'])/'proposed';proposal.mkdir()
for name in ['pyproject.toml','pixi.lock']:shutil.copyfile(root/name,proposal/name)
plans=read('pin-plan.json')
for x in plans:
 if x['root']==str(root):x['proposed']=str(proposal)
write('pin-plan.json',plans)
updates=read('guidance-updates.json');item=next(x for x in updates if x['root']==str(root))
source=next(x for x in updates if x['agents_updated']);pattern=r'<!-- flexlock-release-compatibility -->.*?<!-- /flexlock-release-compatibility -->'
section=re.search(pattern,(Path(source['root'])/'AGENTS.md').read_text(),re.S)[0]
agents=root/'AGENTS.md';old=agents.read_text();key=hashlib.sha256(str(root).encode()).hexdigest()[:16];(r/'agents-before'/f'{key}.md').write_text(old)
new=re.sub(pattern,lambda _:section,old,count=1,flags=re.S) if re.search(pattern,old,re.S) else old+'\n\n'+section+'\n';agents.write_text(new)
feedback=Path(item['feedback']);feedback.write_text('# FlexLock 0.9.3 central rollout feedback — 2026-10-15\n\nStatus: pinned\n\nThe project owner repaired mlflow-pixi to use the shared registry before this retry. That repair was preserved. The FlexLock-only manifest/lock change passes Pixi validation without other lock changes. All four inventoried idle Biomass prefixes now use 0.9.3 and pass record-result, scientific-sidecar preservation, legacy-reader and queue-ownership checks.\n\nSee the compatibility section in AGENTS.md. The retained-wave acceptance remains bounded; package migration does not replay producers or close scientific adoption.\n\nCentral evidence: [rollout report]('+str(r/'report.md')+').\n')
board=Path(item['board']);text=board.read_text();marker='<!-- flexlock093-feedback:'+key+' -->';start=text.index(marker);end=text.find('\n<!-- flexlock093-feedback:',start+len(marker));end=len(text) if end<0 else end
part=text[start:end].replace('Status: restored-review-required.','Status: pinned.');board.write_text(text[:start]+part+text[end:])
item.update(status='pinned',agents_updated=True);write('guidance-updates.json',updates)
shutil.copyfile('/tmp/retry_biomass093_pin.py',r/'retry_biomass_pin.py');shutil.copyfile(__file__,r/'finalize_biomass.py')
print('Merged four installations, preserved initial evidence, updated Biomass guidance and current pin evidence')
