# TODO

<!-- flexlock-adopt:2509_sar_ml--fix_colloc -->
## Highest priority — FLEXLOCK-ADOPT: fix_colloc

- **Accepted:** 2026-10-14, user request; owner: this project's agent. **Status:** queued; central review pending. Prioritize before new experiment expansion, preserving running work and scientific correctness gates.
- **Goal:** migrate active usage to the slimmer workflow. Check actual FlexLock version/import paths and dependency pins first; package migration and scientific adoption are separate. Legacy/example projects may need installation review or an explicit inactive disposition.
- **Guidance:** [shared recipes](/ontap/user/qfebvre/flexlock-execution-validation/docs/workflow_guidelines.md), [release scope](/ontap/user/qfebvre/flexlock-execution-validation/docs/release_0_9_2.md), [handoff contract](/ontap/user/qfebvre/flexlock-execution-validation/docs/project_adoption_handoff.md).
- **Project focus:** Coordinate with the SAR owner and preserve worktree-specific science. Audit suppressed processing exceptions; strict failure versus partial-error accounting needs the pending user decision. No mandatory outcome JSON receipts.
- **Scope:** inventory active callers and selected artifacts; adopt explicit upstream bindings, fresh absolute destinations, correct source/data/lineage evidence and current record readers. Preserve Python config, overrides, presets and sweep files. Keep resources separate; use track/arm/run only where useful. New recipes disable automatic cache search explicitly; retain deliberate validated reuse and existing compatibility callers. Cover remaining active entrypoints or list each deferred caller and reason.
- **Validation:** bounded local/config/failure checks plus one appropriate retained-product or fixture recipe. Verify resolved logger/checkpoint/input paths, actual imports, queue/status/output evidence and unchanged scientific choices. No costly training, full campaigns, scheduler launches, bulk archival or artifact moves are authorized solely by this task.
- **Report back:** keep local evidence in `reports/flexlock-adoption/`; submit `/ontap/user/qfebvre/flexlock-execution-validation/reports/project-adoption/2509_sar_ml--fix_colloc/report.md` with actual source/environment, commits/diffs, caller coverage, artifact bindings, commands/results, limitations and proposed core changes. Write only your own report directory; do not commit the central checkout. Set submitted-for-review; close locally only after central acceptance.
- **Completion:** adopted commands/choices in local AGENTS and accepted central report. Existing protocols, user changes, locks and historical products preserved. If inactive, report the disposition and evidence for central review rather than deleting or silently skipping it.

<!-- /flexlock-adopt:2509_sar_ml--fix_colloc -->


<!-- flexlock-adoption-priority -->
## Highest priority — FLEXLOCK-ADOPT: project-owned workflow migration

- **Accepted:** 2026-10-14, user request; owner: this project's agent.
- **Status:** queued, implementation and central review pending. Do this before new experiment expansion; preserve running work and urgent scientific correctness gates.
- **Goal:** adopt the slimmer FlexLock workflow in active project entrypoints. Runtime 0.9.2 is already installed; verify actual imports, do not confuse package installation with scientific adoption.
- **Shared contract:** [workflow guidelines](/ontap/user/qfebvre/flexlock-execution-validation/docs/workflow_guidelines.md), [release scope](/ontap/user/qfebvre/flexlock-execution-validation/docs/release_0_9_2.md), [review/handoff contract](/ontap/user/qfebvre/flexlock-execution-validation/docs/project_adoption_handoff.md).
- **Project scope:** Focus on enhanced per-SAFE preprocessing and assembly. Freeze membership, bind exact queue IDs, check status/CSV coverage before assembly, and keep distinct record roots. Mandatory item.json receipts were rejected. Current iter_safe_ds/safe_feats suppress exceptions: resolve strict failure versus explicit partial-error accounting with the user before changing those semantics. Preserve split/feature protocols; legacy split validation did not certify leakage safety. Prior split replay and campaign preview did not validate full extraction.
- **Implementation:** inventory active callers/configs and optional policies; add one useful Python entrypoint with concrete upstream bindings and fresh absolute run destinations. Use track/arm/run only where useful. Separate science choices from Slurm resources; preserve overrides and sweep files. Explicitly disable automatic cache search in new recipes; retain intentional compatible reuse. Verify effective input snapshots, producer references, output paths and authoritative queue readers. Expand to remaining active entrypoints or list each deferred caller explicitly.
- **Validation:** bounded local/config/output checks and one appropriate retained-product or small-fixture workflow. Record actual source/environment imports, commands, failures and results. No new expensive training, full extraction campaign, scheduler workload, scientific protocol change or historical artifact relocation is authorized solely by this task; obtain a concrete project budget/decision where required.
- **Report back:** write local evidence in `reports/flexlock-adoption/`, then place a review summary at `/ontap/user/qfebvre/flexlock-execution-validation/reports/project-adoption/sar-ml/report.md`. Include commit/diff paths, caller coverage, selected artifact bindings, checks, remaining blockers and proposed core changes. Do not edit another project's report or claim central approval.
- **Completion:** update local AGENTS with adopted commands/choices; submit report for review here. Mark submitted-for-review first; close this task only after central acceptance, recording that decision in the local done board.

<!-- /flexlock-adoption-priority -->


Accepted implementation scope only. Promote an item from [IDEAS.md](IDEAS.md)
after its protocol, constraints, compatibility effects, and validation plan have
been agreed. Record completed investigations and durable decisions in
[DONE.md](DONE.md).

## Active

No implementation task has yet been formally accepted through this planning
folder.

## Decisions required before the next training campaign

Two choices are one-way doors and should be written down before looking at new
results:

1. Which periods, months, or events are reserved as the untouched test set
   ([I1](IDEAS.md#i1--leakage-resistant-data-split)). Once their performance is
   inspected, they have effectively become development data.
2. Which spatial and temporal gates, source versions, deduplication rules, and
   quality filters define the frozen independent validation set
   ([I2](IDEAS.md#i2--frozen-independent-measurement-validation-set)). Changing
   collocation rules during an ablation campaign changes the metric itself.

## Recommended promotion order

1. Promote I1 as a leakage audit and split-protocol task. Do not tune model
   architecture or high-sea losses before this baseline is trustworthy.
2. Promote I2 as a frozen altimeter/buoy validation-product task, including
   stable identifiers and a versioned manifest.
3. Run I3, the offline gradient-target validity diagnostic. It requires no new
   training and can proceed while I1 and I2 data products are prepared.
4. Add the small I4 anti-collapse metrics to the re-baseline run.
5. Promote I5 only after I1-I3 settle the split, scoring metric, and treatment
   of the gradient loss.
6. Audit calibration in I6 before choosing the production/export head in I7.
7. Promote I8 spectrum consolidation independently when the current alignment
   risk or Lustre metadata cost is confirmed on the active data path.
8. Build the I10/I11 result products before implementing the proposed SAR-ML
   explorers; the UI should consume stable products rather than repair joins.

## Promotion template

### T<number> — Title

- **Accepted:** YYYY-MM-DD
- **Origin:** `IDEAS.md` section

**Goal:**

**Accepted scope:**

**Non-goals:**

**Compatibility and invalidation:**

**Validation:**

**Completion criteria:**
