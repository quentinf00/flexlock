from pathlib import Path
import json,re,hashlib,shutil
r=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout')
def read(n):return json.loads((r/n).read_text())
def write(n,v):(r/n).write_text(json.dumps(v,indent=2)+'\n')
installs=read('maxss-installation-results.json');assert len(installs)==5 and all(x['status']=='installed' for x in installs)
for name in ['installation-results.json','pin-results.json','pin-plan.json','guidance-updates.json','prefix-preflight.json']:
 backup=r/name.replace('.json','-before-maxss.json');assert not backup.exists();shutil.copyfile(r/name,backup)
by={x['prefix']:x for x in installs};write('installation-results.json',[by.get(x['prefix'],x) for x in read('installation-results.json')]);write('prefix-preflight.json',read('maxss-prefix-preflight.json'))
retry=read('maxss-pin-retry.json');by={x['root']:x for x in retry};write('pin-results.json',[by.get(x['root'],x) for x in read('pin-results.json')])
plans=read('pin-plan.json')
for x in plans:
 if x['root'] in by:x.update(proposed=by[x['root']]['proposed'],defer=False)
write('pin-plan.json',plans)
updates=read('guidance-updates.json');source=next(x for x in updates if x['agents_updated']);pattern=r'<!-- flexlock-release-compatibility -->.*?<!-- /flexlock-release-compatibility -->';section=re.search(pattern,(Path(source['root'])/'AGENTS.md').read_text(),re.S)[0]
for item in updates:
 if item['root'] not in by:continue
 root=Path(item['root']);agents=root/'AGENTS.md';old=agents.read_text();key=hashlib.sha256(str(root).encode()).hexdigest()[:16];(r/'agents-before'/f'{key}.md').write_text(old)
 specific=''
 if root.name in ('maxss-ml','neural-field'):
  specific='\n\nPreserve the MaxSS launch convention: activate the main hpc environment, put the\nneural-field src first on PYTHONPATH for NF work, and execute from\n/scale/user/qfebvre/projects/250930_maxss_era5pp. Existing results_hafs and\nvalidation-panel paths remain relative to that experiment root. Shared dependency\npaths and scientific products are unchanged. The worktree standalone prefixes\nare upgraded too; this does not validate standalone scientific imports.\n'
 newsection=section.replace('<!-- /flexlock-release-compatibility -->',specific+'<!-- /flexlock-release-compatibility -->')
 assert len(re.findall(pattern,old,re.S))==1
 agents.write_text(re.sub(pattern,lambda _:newsection,old,count=1,flags=re.S))
 Path(item['feedback']).write_text('# FlexLock 0.9.3 central rollout feedback — 2026-10-15\n\nStatus: pinned\n\nDeferred MaxSS job 1370177 completed successfully at 2026-10-15T15:53:13 (scheduler time). A fresh queue check found no replacement MaxSS job. The main, neural-field and tcwind manifest/lock pins pass Pixi validation without non-FlexLock lock changes. All five family prefixes now use 0.9.3 and pass installed-package record-result, sidecar preservation, legacy-reader and queue-ownership checks.\n\nKeep the documented main-hpc/worktree-src launch convention. This release does not replay GPU training, reorganize completed results or close deferred scientific callers. Existing bounded central acceptance remains scoped as reviewed.\n\nCentral evidence: [rollout report]('+str(r/'report.md')+').\n')
 board=Path(item['board']);text=board.read_text();marker='<!-- flexlock093-feedback:'+key+' -->';start=text.index(marker);end=text.find('\n<!-- flexlock093-feedback:',start+len(marker));end=len(text) if end<0 else end;part=text[start:end].replace('Status: deferred-active.','Status: pinned.');board.write_text(text[:start]+part+text[end:])
 item.update(status='pinned',agents_updated=True)
write('guidance-updates.json',updates);shutil.copyfile('/tmp/retry_maxss093.py',r/'retry_maxss_pin.py');shutil.copyfile(__file__,r/'finalize_maxss.py');print('Merged five installations and three project pins/guidance updates')
