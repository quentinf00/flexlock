from pathlib import Path
import json, hashlib
central=Path('/ontap/user/qfebvre/flexlock-execution-validation')
evidence=central/'reports/2026-10-14-project-handoffs'
evidence.mkdir(parents=True,exist_ok=True)
projects=[
('hafs-jepa','/scale/user/qfebvre/projects/260324_jepa/hafs-jepa/plans/TODO.md',['/scale/user/qfebvre/projects/260324_jepa/hafs-jepa'], 'Audit current training/probe scripts as well as FlexLock configs; some workflows may bypass FlexLock. Start with retained-checkpoint evaluation and explicit corpus/split bindings. Preserve channel/band choices, probe protocol and all existing models. Prior inspection covered installation/config inventory only, not scientific replay.'),
('maxss-ml','/scale/user/qfebvre/projects/250930_maxss_era5pp/plans/todo.md',['/scale/user/qfebvre/projects/250930_maxss_era5pp/maxss-ml','/scale/user/qfebvre/projects/250930_maxss_era5pp/maxss-ml/.claude/worktrees/neural-field'], 'Cover main and neural-field entrypoints with separate import-path checks. Preserve main-hpc/worktree-src launch convention and experiment-root cwd; verify fresh save_dir reaches logger/checkpoint paths. Retain existing models/panels and dataset locations. Prior validation checked neural-field config/signature/path propagation, not training/inference. Existing scientific P0/P0b correctness gates remain prerequisites for affected runs.'),
('sar-ml','/scale/user/qfebvre/projects/2509_sar_ml/plans/TODO.md',['/scale/user/qfebvre/projects/2509_sar_ml/sar-ml-enhanced'], 'Focus on enhanced per-SAFE preprocessing and assembly. Freeze membership, bind exact queue IDs, check status/CSV coverage before assembly, and keep distinct record roots. Mandatory item.json receipts were rejected. Current iter_safe_ds/safe_feats suppress exceptions: resolve strict failure versus explicit partial-error accounting with the user before changing those semantics. Preserve split/feature protocols; legacy split validation did not certify leakage safety. Prior split replay and campaign preview did not validate full extraction.'),
('sst-ml','/scale/user/qfebvre/projects/251218_sst/plans/TODO.md',['/scale/user/qfebvre/projects/251218_sst/sst_ml_mapping','/scale/user/qfebvre/projects/251218_sst/sst_ml_zarrpatch'], 'Coordinate mapping and zarrpatch ownership; start with the active zarrpatch path and explicitly document coverage of mapping. Replace implicit preparation selection with concrete accepted producers; update root anchors before selecting detached consumers. Preserve T15/T20 checkpoints/evaluation paths, membership and preprocessing. Prior frozen-matchup reassessment matched baseline; training/preparation was not replayed. Keep the user requirement to submit through FlexLock Slurm backend.')]
updates=[]
for slug,board,roots,specific in projects:
 p=Path(board); before=p.read_text(); marker='<!-- flexlock-adoption-priority -->'
 assert marker not in before
 block=f'''{marker}
## Highest priority — FLEXLOCK-ADOPT: project-owned workflow migration

- **Accepted:** 2026-10-14, user request; owner: this project's agent.
- **Status:** queued, implementation and central review pending. Do this before new experiment expansion; preserve running work and urgent scientific correctness gates.
- **Goal:** adopt the slimmer FlexLock workflow in active project entrypoints. Runtime 0.9.2 is already installed; verify actual imports, do not confuse package installation with scientific adoption.
- **Shared contract:** [workflow guidelines]({central}/docs/workflow_guidelines.md), [release scope]({central}/docs/release_0_9_2.md), [review/handoff contract]({central}/docs/project_adoption_handoff.md).
- **Project scope:** {specific}
- **Implementation:** inventory active callers/configs and optional policies; add one useful Python entrypoint with concrete upstream bindings and fresh absolute run destinations. Use track/arm/run only where useful. Separate science choices from Slurm resources; preserve overrides and sweep files. Explicitly disable automatic cache search in new recipes; retain intentional compatible reuse. Verify effective input snapshots, producer references, output paths and authoritative queue readers. Expand to remaining active entrypoints or list each deferred caller explicitly.
- **Validation:** bounded local/config/output checks and one appropriate retained-product or small-fixture workflow. Record actual source/environment imports, commands, failures and results. No new expensive training, full extraction campaign, scheduler workload, scientific protocol change or historical artifact relocation is authorized solely by this task; obtain a concrete project budget/decision where required.
- **Report back:** write local evidence in `reports/flexlock-adoption/`, then place a review summary at `{central}/reports/project-adoption/{slug}/report.md`. Include commit/diff paths, caller coverage, selected artifact bindings, checks, remaining blockers and proposed core changes. Do not edit another project's report or claim central approval.
- **Completion:** update local AGENTS with adopted commands/choices; submit report for review here. Mark submitted-for-review first; close this task only after central acceptance, recording that decision in the local done board.

<!-- /flexlock-adoption-priority -->

'''
 first=before.index('\n')+1
 after=before[:first]+'\n'+block+before[first:]
 backup=evidence/(slug+'-todo-before.md');backup.write_text(before)
 p.write_text(after)
 updates.append(dict(project=slug,path=str(p),before_sha256=hashlib.sha256(before.encode()).hexdigest(),after_sha256=hashlib.sha256(after.encode()).hexdigest()))
 for root in roots:
  a=Path(root)/'AGENTS.md';s=a.read_text();addition=f'''\n<!-- flexlock-adoption-task -->
## Next priority: project-owned FlexLock adoption

The authoritative highest-priority task is FLEXLOCK-ADOPT in [{p.name}]({p}).
Follow that task and [central handoff contract]({central}/docs/project_adoption_handoff.md).
Implement within this project's scope and report to `{central}/reports/project-adoption/{slug}/report.md`
for central review. Installed 0.9.2 does not establish workflow/scientific adoption.
Preserve existing protocols, user changes and artifacts; do not infer authorization
for expensive runs or broad cleanup. Other project instructions remain applicable.
<!-- /flexlock-adoption-task -->
'''
  assert '<!-- flexlock-adoption-task -->' not in s
  a.write_text(s+addition)
print(json.dumps(updates,indent=2))
(evidence/'updates.json').write_text(json.dumps(updates,indent=2))
