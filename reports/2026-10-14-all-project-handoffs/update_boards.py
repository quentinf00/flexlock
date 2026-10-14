from pathlib import Path
import json,tomllib,hashlib
central=Path('/ontap/user/qfebvre/flexlock-execution-validation'); evidence=central/'reports/2026-10-14-all-project-handoffs';evidence.mkdir(parents=True,exist_ok=True)
roots={Path(r['project']).resolve() for r in json.loads((central/'reports/2026-10-13-project-migration/agents-updates.json').read_text())}
for m in Path('/scale/user/qfebvre/projects').glob('*/*/pyproject.toml'):
 try: d=tomllib.loads(m.read_text())
 except tomllib.TOMLDecodeError: continue
 if d.get('project',{}).get('name','').lower()!='flexlock' and 'flexlock' in m.read_text().lower():roots.add(m.parent.resolve())
plan=[]
for root in sorted(roots):
 agents=root/'AGENTS.md';text=agents.read_text() if agents.exists() else ''
 if '<!-- flexlock-adoption-task -->' in text:continue
 slug=root.parent.name+'--'+root.name
 board=next((b/n for b in [root,root.parent] for n in ['plans/TODO.md','plans/todo.md','TODO.md','todo.md'] if (b/n).is_file()),root/'plans/TODO.md')
 local='Start with one retained-input or small-fixture workflow; audit active callable/CLI/worker entrypoints before reorganizing configs.'
 if 'biomass' in str(root):local='Freeze listing membership and check per-item coverage before aggregation; preserve existing feature/model bindings and historical batch products.'
 elif 'nextgems' in str(root):local='Keep smoke/full/subset month sweep files and explicit membership; do not create one config per month. Preserve existing data paths.'
 elif 'jepa' in str(root) or root.name=='le-tc-wm':local='Start with retained-checkpoint evaluation and concrete corpus/split bindings; preserve training/evaluation protocols.'
 elif root.name=='tcwind_benchtools':local='Coordinate with MaxSS on shared dependencies and retained diagnostic products; do not duplicate or supersede its accepted adoption task.'
 elif 'sar' in str(root):local='Coordinate with the SAR owner and preserve worktree-specific science. Audit suppressed processing exceptions; strict failure versus partial-error accounting needs the pending user decision. No mandatory outcome JSON receipts.'
 elif root.name=='project_template':local='Audit malformed/duplicate dependency tables and pin drift before syncing the environment; update template-generated examples without inventing scientific workloads.'
 plan.append(dict(project=slug,root=str(root),board=str(board),agents=str(agents),local=local))
(evidence/'plan.json').write_text(json.dumps(plan,indent=2))
if '--apply' not in __import__('sys').argv:
 print(json.dumps(plan,indent=2));raise SystemExit
updates=[]
for i,row in enumerate(plan):
 board=Path(row['board']);before=board.read_text() if board.exists() else '# TODO\n'
 marker='<!-- flexlock-adopt:'+row['project']+' -->'
 block=f'''{marker}
## Highest priority — FLEXLOCK-ADOPT: {Path(row['root']).name}

- **Accepted:** 2026-10-14, user request; owner: this project's agent. **Status:** queued; central review pending. Prioritize before new experiment expansion, preserving running work and scientific correctness gates.
- **Goal:** migrate active usage to the slimmer workflow. Check actual FlexLock version/import paths and dependency pins first; package migration and scientific adoption are separate. Legacy/example projects may need installation review or an explicit inactive disposition.
- **Guidance:** [shared recipes]({central}/docs/workflow_guidelines.md), [release scope]({central}/docs/release_0_9_2.md), [handoff contract]({central}/docs/project_adoption_handoff.md).
- **Project focus:** {row['local']}
- **Scope:** inventory active callers and selected artifacts; adopt explicit upstream bindings, fresh absolute destinations, correct source/data/lineage evidence and current record readers. Preserve Python config, overrides, presets and sweep files. Keep resources separate; use track/arm/run only where useful. New recipes disable automatic cache search explicitly; retain deliberate validated reuse and existing compatibility callers. Cover remaining active entrypoints or list each deferred caller and reason.
- **Validation:** bounded local/config/failure checks plus one appropriate retained-product or fixture recipe. Verify resolved logger/checkpoint/input paths, actual imports, queue/status/output evidence and unchanged scientific choices. No costly training, full campaigns, scheduler launches, bulk archival or artifact moves are authorized solely by this task.
- **Report back:** keep local evidence in `reports/flexlock-adoption/`; submit `{central}/reports/project-adoption/{row['project']}/report.md` with actual source/environment, commits/diffs, caller coverage, artifact bindings, commands/results, limitations and proposed core changes. Write only your own report directory; do not commit the central checkout. Set submitted-for-review; close locally only after central acceptance.
- **Completion:** adopted commands/choices in local AGENTS and accepted central report. Existing protocols, user changes, locks and historical products preserved. If inactive, report the disposition and evidence for central review rather than deleting or silently skipping it.

<!-- /flexlock-adopt:{row['project']} -->

'''
 assert marker not in before
 (evidence/f'{i}-board-before.md').write_text(before)
 board.parent.mkdir(parents=True,exist_ok=True)
 split=before.find('\n')+1
 board.write_text(before[:split]+'\n'+block+before[split:])
 a=Path(row['agents']);old=a.read_text() if a.exists() else ''
 (evidence/f'{i}-agents-before.md').write_text(old)
 new=old+f'''\n<!-- flexlock-adoption-task -->
## Next priority: FLEXLOCK-ADOPT

The accepted highest-priority task for this checkout is in [{board.name}]({board}).
Follow [central handoff]({central}/docs/project_adoption_handoff.md) and report to
`{central}/reports/project-adoption/{row['project']}/report.md` for review.
Verify actual installation before adoption; preserve scientific protocols and artifacts.
Other project instructions remain applicable. No expensive run or broad cleanup is
implicitly authorized by this task.
<!-- /flexlock-adoption-task -->
'''
 a.write_text(new)
 updates.append(dict(row,board_before_sha256=hashlib.sha256(before.encode()).hexdigest(),board_after_sha256=hashlib.sha256(board.read_bytes()).hexdigest()))
(evidence/'updates.json').write_text(json.dumps(updates,indent=2));print('Added handoffs:',len(updates))
