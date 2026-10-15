import json,re,hashlib
from pathlib import Path
r=Path('/ontap/user/qfebvre/flexlock-execution-validation');report=r/'reports/2026-10-15-release-rollout';rows=json.loads((report/'pin-results.json').read_text());backups=report/'agents-before';backups.mkdir(exist_ok=True);updates=[]
for row in rows:
 root=Path(row['root']);status=row['status'];agents=root/'AGENTS.md';identity=hashlib.sha256(str(root).encode()).hexdigest()[:16]
 if status=='pinned':
  note='''The project manifest and lock pin FlexLock 0.9.3. Inventoried idle prefixes were
upgraded and passed installed-package checks. Scientific adoption remains scoped
to the project's separately reviewed recipes; package migration is not a replay.

- Return payloads now live in the authoritative record's result section. Use
  load_record / RunRecord.load_results; historical results.json remains readable.
  Callable-owned results.json is preserved. Do not declare a core-generated
  results.json as a required product; core no longer creates it.
- Source capture and comparison share per-repository include/exclude rules.
  Nested configured targets in Git/src/editable checkouts are discovered.
  Auto scopes contain target source files; declare imported helpers/subprocess
  repositories explicitly. Explicit full-repo declarations still request full
  non-ignored capture. Review source scope before a new scientific campaign.
- Concrete producer records still bind by full digest. Results finalize before
  completion. Completed composite stages can feed nested submissions while the
  parent runs; unrelated active owners remain guarded. Terminal queue export
  preserves unresolved references rather than masking the original failure.
- Existing fresh-destination, queue/status/output coverage and held-job ownership
  rules remain. Automatic cache search is not removed; new recipes pass False.
- Update all readers before using new result records across environments. Do not
  move/rewrite historical products or infer missing scientific provenance.
'''
  section='<!-- flexlock-release-compatibility -->\n## FlexLock release compatibility (2026-10-15; 0.9.3)\n\n'+note+'\nRelease: [0.9.3]('+str(r/'docs/release_0_9_3.md')+').\nMigration: [record/source contract]('+str(r/'docs/record_and_source_scope_migration.md')+').\n<!-- /flexlock-release-compatibility -->'
  old=agents.read_text() if agents.exists() else ''
  (backups/(identity+'.md')).write_text(old)
  pattern=r'<!-- flexlock-release-compatibility -->.*?<!-- /flexlock-release-compatibility -->'
  new=re.sub(pattern,lambda _:section,old,count=1,flags=re.S) if re.search(pattern,old,re.S) else old+'\n\n'+section+'\n'
  if 'sar-ml-enhanced' in str(root):
   start=new.find('- Do not multi-select stages with promised producer snapshots')
   if start>=0:
    stop=new.find('\n\n',start)
    if stop<0:stop=len(new)
    new=new[:start]+'- FlexLock 0.9.3 now validates the six-stage local CLI chain on the bounded\n  NetCDF fixture, including completed-stage bindings for nested extraction.\n  Slurm extraction remains asynchronous: submit it separately and check coverage\n  before assembly; the local controller remains a supported alternative.'+new[stop:]
  agents.write_text(new)
 elif status=='deferred-active':
  note='''Upgrade remains deferred: MaxSS job 1370177 uses the main HPC environment.
The main/neural-field and associated tool environments/manifests remain at their
previous version. After running/pending jobs finish, recheck scheduler state and
use the prepared 0.9.3 wheel/pin candidates. Do not modify active environments.
'''
 else:
  note='''Upgrade remains deferred and the original manifest/lock were restored. Pixi
could not validate the 0.9.3 pin because of a pre-existing project dependency issue.
'''
  if 'project_template' in str(root):
   note+='''The template has duplicate dev dependency tables and an unsatisfiable
better-exceptions>=0.4.0,<0.5 constraint (resolver finds <=0.3.3). Review the intended
constraint and repair the old Conda FlexLock provider/lock before retrying. The
prepared candidate merges the duplicate tables without dropping their entries.
'''
  else:
   note+='''mlflow-pixi still points at the removed personal registry checkout. MOVED.md
identifies the shared registry at /scale/project/lops-siam-model-registry; its
mlflow_pixi checkout exists there. The project owner should update the dependency
binding to that canonical location, validate the model-runtime contract and lock,
then retry the reviewed FlexLock pin. Do not revive the archived registry or
silently change scientific producer/model selection.
'''
 feedback=root/'reports/flexlock-adoption/release-0.9.3-feedback.md';feedback.parent.mkdir(parents=True,exist_ok=True)
 assert not feedback.exists(),feedback
 feedback.write_text('# FlexLock 0.9.3 central rollout feedback — 2026-10-15\n\nStatus: '+status+'\n\n'+note+'\nCentral evidence: ['+str(report/'report.md')+']('+str(report/'report.md')+').\n')
 if 'sar-ml-enhanced' in str(root):
  with feedback.open('a') as stream:
   stream.write('\nThe corrected acceptance helper and the six-stage local CLI chain pass on tiny NetCDF fixtures. Continue FLEXLOCK-LIFECYCLE next: implement and validate reusable collocation, portable release packaging and bounded L2 processing against the [central lifecycle draft](' + str(r/'docs/workflow_lifecycle.md') + '). These stages are not certified by the preprocessing check.\n')

 # Existing project adoption boards already contain owner tasks. Add a link,
 # preserving those tasks and their scope rather than claiming their closure.
 candidates=[root/'plans/TODO.md',root/'plans/todo.md',root/'TODO.md']
 if '250930_maxss_era5pp' in str(root):candidates.insert(0,Path('/scale/user/qfebvre/projects/250930_maxss_era5pp/plans/todo.md'))
 if '2509_sar_ml' in str(root):candidates.insert(0,Path('/scale/user/qfebvre/projects/2509_sar_ml/plans/TODO.md'))
 if '251218_sst' in str(root):candidates.insert(0,Path('/scale/user/qfebvre/projects/251218_sst/plans/TODO.md'))
 if '2508_nextgems' in str(root):candidates.insert(0,Path('/scale/user/qfebvre/projects/2508_nextgems/plans/TODO.md'))
 if '260617_biomass' in str(root):candidates.insert(0,Path('/scale/user/qfebvre/projects/260617_biomass/plans/TODO.md'))
 board=next((p for p in candidates if p.exists()),None)
 if board:
  marker='<!-- flexlock093-feedback:'+identity+' -->';text=board.read_text();assert marker not in text
  board.write_text(text+'\n'+marker+'\n## FlexLock 0.9.3 rollout — '+root.name+'\n\nStatus: '+status+'. Read [central release feedback]('+str(feedback)+') before new work. Package migration does not close scientific adoption. Continue the existing project-owned adoption task; resolve any listed blocker before environment synchronization.\n')
 updates.append(dict(root=str(root),status=status,agents_updated=status=='pinned',feedback=str(feedback),board=str(board) if board else None))
 print(root.name,status,flush=True)
(report/'guidance-updates.json').write_text(json.dumps(updates,indent=2)+'\n')
