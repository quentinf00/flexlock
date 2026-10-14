import json, hashlib
from pathlib import Path
core=Path('/ontap/user/qfebvre/flexlock-execution-validation')
report=core/'reports/2026-10-14-project-workflows'
rows=[]
for batch in ['2026-10-13-project-migration','2026-10-14-maxss-migration']:
 rows+=json.loads((core/'reports'/batch/'agents-updates.json').read_text())
seen=set(); results=[]
for row in rows:
 p=Path(row['agents']); key=p.resolve()
 if key in seen: continue
 seen.add(key); old=p.read_text(); name=Path(row['project']).name
 local='Start with one Python config entrypoint and explicit retained-input bindings. Add separate stage or track modules only when actual reuse warrants them. Keep existing scientific parameters, split definitions and artifact paths during the first bounded comparison.'
 if name.startswith('biomass'): local+=' Freeze listing membership and require accepted item coverage before feature aggregation; keep historical batch outputs.'
 elif name=='nextgems_tc': local+=' Keep smoke/full/subset month sweep files and explicit selected-month membership; do not create one config per month.'
 elif name=='sar-ml-enhanced': local+=' Use distinct receipt directories for split, each SAFE extraction, and each train/validation/test dataset. Extraction adoption requires explicit produced/legitimate-empty outcomes and a coverage gate before prepare_dataset, which currently skips missing CSVs. Missing output alone does not prove emptiness. Preserve the existing split protocol; the validated legacy split is not a leakage-safety certification.'
 elif name.startswith('sst_ml'): local+=' Begin with retained-matchup reassessment bindings; keep training checkpoints and T15/T20 evaluation paths. Separate scientific arms from resource profiles. Historical save_dir values may be relative: use the concrete selected producer directory and document the historical base.'
 elif name in ['geo-jepa','hafs-jepa','le-tc-wm']: local+=' Bind retained pretraining checkpoints and split definitions explicitly; start with a bounded retained-checkpoint evaluation before config cleanup.'
 elif name in ['maxss-ml','neural-field']: local+=' Keep the main-hpc/worktree-src launch convention documented above and its experiment-root working directory. Import the selected arm config explicitly; logger/checkpoint paths must follow the fresh save_dir. Preserve validation panels and completed models.'
 elif name=='tcwind_benchtools': local+=' Start with a retained-input diagnostic entrypoint and keep shared dependency source paths stable.'
 text=f'''\n\n<!-- flexlock-project-workflow -->
## FlexLock project workflow (0.9.2; 2026-10-14)

Shared recipes: [workflow guidelines]({core}/docs/workflow_guidelines.md).
Release scope: [0.9.2]({core}/docs/release_0_9_2.md).
Project transition proposals: [review draft]({core}/reports/2026-10-13-workflow-validation/TRANSITION.md).
The guidelines are maintained centrally; keep concrete project choices and exceptions here.
Research, knowledge and reporting instructions elsewhere in this file continue to apply.

- Use a fresh absolute run destination; track/arm/run is a useful naming convention,
  not a required schema or an automatic architecture selector.
- Select concrete upstream runs in configuration. Keep data snapshots tied to effective
  callable input arguments, and producer lineage tied to the corresponding selection.
  Preserve direct run_lock interpolation, overrides and sweep-file usage.
- Freeze file-list campaign membership. Check accepted outcomes for every expected item
  before aggregation; queue completion alone does not establish scientific coverage.
- Keep resource profiles separate from scientific choices. For different stage resources,
  use a small orchestration script with --after and persisted accepted job IDs. A reporting
  failure after submission must not cause blind resubmission.
- Retain original locks and artifacts. Before archiving config entrypoints, audit callers;
  before moving outputs, audit upstream references and active queue ownership.

Project starting point: {local}

This section guides new work; it does not assert that all historical workflows have
been replayed or that production configs/artifacts have been reorganized. Record actual
entrypoints, selected artifact paths and validation outcomes here when a project adopts
its first recipe; do not infer missing historical provenance.
<!-- /flexlock-project-workflow -->
'''
 if '<!-- flexlock-project-workflow -->' in old:
  a=old.index('<!-- flexlock-project-workflow -->'); b=old.index('<!-- /flexlock-project-workflow -->',a)+len('<!-- /flexlock-project-workflow -->'); new=old[:a]+text.strip()+old[b:]
 else: new=old+text
 backup=report/'before'/str(len(results)); backup.parent.mkdir(parents=True,exist_ok=True); backup.write_text(old)
 p.write_text(new)
 assert p.read_text()==new
 results.append({'agents':str(p),'physical_path':str(key),'before_sha256':hashlib.sha256(old.encode()).hexdigest(),'after_sha256':hashlib.sha256(new.encode()).hexdigest(),'backup':str(backup),'preserved_existing_text':old in new})
(report/'updates.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'updated_distinct_files':len(results),'existing_text_preserved':all(r['preserved_existing_text'] for r in results)}))
