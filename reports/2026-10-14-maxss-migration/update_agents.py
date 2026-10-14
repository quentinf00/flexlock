import json
from pathlib import Path
CORE=Path('/ontap/user/qfebvre/flexlock-execution-validation')
REPORT=CORE/'reports/2026-10-14-maxss-migration'
main=Path('/ontap/user/qfebvre/work/projects/250930_maxss_era5pp/maxss-ml')
roots=[main,main/'.claude/worktrees/neural-field']
text='''<!-- flexlock-release-compatibility -->
## FlexLock migration and neural-field workflow (2026-10-14)

FlexLock 0.9.2 is installed in the previously shared MaxSS environments. Both
main and neural-field manifests/locks pin the reviewed local wheel. The
neural-field manifest's tcwind_benchtools and zarrpatch paths are now absolute
references to the same shared packages used by its existing launch convention.
The worktree's standalone environment has not been installed by this migration.

Preserve the existing launch convention when using the shared environment:
activate the main hpc environment, put the neural-field src first on PYTHONPATH,
and execute from /scale/user/qfebvre/projects/250930_maxss_era5pp. Existing
results_hafs and validation-panel paths are relative to that experiment root.
Check actual FlexLock and scientific module import paths before submitting.

Compatibility changes:

- Destination/queue ownership is checked before scheduler submission. Use a fresh
  absolute save_dir set before config resolution. --force cannot bypass active
  queue ownership. Preserve completed checkpoints, panels and run records.
- Concrete run_lock references bind selected producer records before submission;
  changed/missing producers cause failure. --after keeps the exact future path.
- Output contracts and authoritative records gate successful reuse; submission
  does not imply scientific completion. Inspect task rows and stage receipts.
- Fresh nested outputs may omit .flexlock-queue.json. Use shared FlexLock record
  readers; consumers of queue layout 2 need 0.9.1+. Keep pending outputs with
  their ancestor queue; audit dependencies before moving historical artifacts.
- Python configs, py2cfg, @ presets and sweeps remain supported. Cache/pipeline
  retirement is still pending; this deployment does not remove their old APIs.
- FlexLock no longer depends on pandas; scientific and optional MLflow packages
  retain their own requirements.

Validation checked installed readers and the actual neural-field cfg_smoke source,
callable signature, and logger/checkpoint paths after a fresh save_dir override.
Completed-run artifacts were hashed and remained unchanged. Training and inference
were not replayed. Dirty/untracked scientific files were preserved and not committed.

For new organization, begin with one imported arm config, explicit retained input
bindings and a fresh track/arm/run directory. An arm label does not select an
architecture by itself. Keep legacy launch modules and result paths during the
pilot. Review data, checkpoint and cached-panel compatibility before any new run.

Evidence and proposal:
/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-14-maxss-migration/
/ontap/user/qfebvre/workflow-transition-validation/20261013/TRANSITION.md
<!-- /flexlock-release-compatibility -->
'''
changes=[]
for root in roots:
 f=root/'AGENTS.md';old=f.read_text() if f.exists() else ''
 assert '<!-- flexlock-release-compatibility -->' not in old
 backup=REPORT/'agents-before'/('main' if root==main else 'neural-field')/'AGENTS.md'
 backup.parent.mkdir(parents=True,exist_ok=True);backup.write_text(old)
 f.write_text(old.rstrip()+'\n\n'+text)
 changes.append(dict(project=str(root),agents=str(f),created=not bool(old)))
(REPORT/'agents-updates.json').write_text(json.dumps(changes,indent=2)+'\n')
print(json.dumps(changes,indent=2))
