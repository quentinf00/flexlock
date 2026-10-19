# Project-owned adoption and central review

Accepted 2026-10-14. The agents owning each consuming project own scientific workflow adoption.
The initial HAFS-JEPA, MaxSS (including neural-field), SAR and SST handoffs
are extended to all additionally discovered consumers. Their existing project boards each
contain highest-priority FLEXLOCK-ADOPT; checkout AGENTS files link those boards.
This document defines the shared handoff, not a second project TODO board.

Runtime adoption is already installed across the inventoried environments.
Workflow adoption requires actual caller/config changes and bounded checks.
Scientific acceptance is a separate conclusion; do not infer it from installation,
configuration resolution, scheduler acceptance or a successful toy test.

The local **0.10.0rc1 candidate** now removes automatic cache search, partial-stage
marker resume and chained fanout. It has not been rolled out. Before a candidate
upgrade, clean obsolete kwargs (including smart_run=False), select retained producers
explicitly and check recovery scripts against the
[breaking-change notes](release_0_10_0rc1.md). Do not mechanically replace cache hits
with expensive fresh scientific computation. Installed 0.9.3 evidence remains dated
evidence for that release, not acceptance of the new candidate.

## Scope and evidence

Read the [shared recipes](workflow_guidelines.md) and [current release scope](release_0_9_3.md).
Inventory active CLI/Python/script entrypoints and retained-product readers. Record
which use implicit caching, detached-config mutation, pipeline markers or direct
queue-pointer reads. Keep supported config/override/sweep usage; migrate toward
concrete selected artifacts and explicit resource orchestration where applicable.
The 0.9.3 rollout report (internal validation evidence) records
installed versions, project feedback and dependency blockers. Check the actual
project version before writing new result records; package rollout does not close
scientific adoption.

Start with one useful workflow, then list remaining active callers and their status.
Do not impose track/arm/run folders or split every config into many modules.

Use fresh absolute output paths and check logger/checkpoint/data paths after
resolution. Verify source, declared data and selected upstream provenance using
actual installed readers, including task DB and parent references. Capture imported
versions/files and dirty-code identity. Preserve original locks and scientific
inputs/products; explain historical provenance gaps instead of filling them in.

No blanket expensive scientific launch or artifact reorganization is authorized
by the handoff. Use existing project budgets/authorization and bounded local checks;
request a concrete decision when science semantics or compute scope would change.
SAR error handling remains pending: current read/feature helpers suppress exceptions.
Mandatory per-item outcome JSON is not required, and cannot repair those errors.

## Fresh baselines after API stabilization

Decision, 2026-10-16: aim for fresh end-to-end project pipelines once the FlexLock
API and workflow contracts stabilize, rather than building a permanent layer of
legacy scientific-producer adapters into FlexLock. Pre-1.0 compatibility work must
not force the core to preserve every historical project convention.

Until then, consuming an old product with explicitly imperfect provenance is
acceptable as a project decision. Track the effective input's current identity
and known origin; state missing historical source/data/environment evidence.
Project-specific acceptance/adaptation code belongs in that project. Do not
manufacture an upstream record or rewrite old locks to make the lineage look complete.
Retained-product pilots establish bounded transition evidence, not the final baseline.

At stabilization, each project should plan its whole pipeline from declared raw
inputs through downstream products, with a pinned FlexLock version, project
source/environment, frozen membership and fresh output destinations. Require current
bookkeeping and concrete upstream bindings throughout that new chain. Check coverage
and scientifically meaningful outputs against retained references before promoting
the new execution as the baseline for future work. Preserve useful historical
artifacts separately; a fresh baseline does not require deleting them.

Full reruns remain project-owned work with their compute scope agreed separately.
No full scientific rerun is launched by the current package migration or this guidance.
Existing bounded acceptance and reported evidence gaps remain accurate as dated.

## Report back

Keep implementation and detailed evidence in the owning project, preferably
`reports/flexlock-adoption/`. Write a concise central summary to:

`<project-owned evidence path>`

Initial project keys: `hafs-jepa`, `maxss-ml`, `sar-ml`, `sst-ml`. Additional keys
and owning boards are in the handoff inventory (internal validation evidence).
Each agent writes only its
own report directory. Do not commit the central checkout, modify other reports,
or change core defaults unilaterally; the central reviewer integrates submissions.

Include:

- Actual checkout, worktree, environment, version/import paths and commit/diff.
- Entry points inspected, migrated and explicitly deferred, with reasons.
- Example config/command, selected artifact bindings and fresh run organization.
- Checks executed, observed outcomes and links to receipts/local evidence.
- Scientific invariants preserved, historical artifacts untouched, remaining gaps.
- Proposed FlexLock/core or shared-guideline changes requiring central review.

Set the local task to submitted-for-review. Central review checks evidence,
compatibility, minimality and whether scientific claims fit validation. Record
acceptance or requested follow-up in the submitted report; close the local task
only after acceptance. A core defect goes to the FlexLock owner rather than a
project-specific workaround that hides incorrect provenance or status.

## Prior inspection depth

| Project | Existing evidence | Still needed |
|---|---|---|
| HAFS-JEPA | Installed release, config inventory and workflow guidance | Active trainer/probe caller audit and retained-checkpoint recipe validation |
| MaxSS / neural-field | Installed release; actual neural-field config/signature and output-path propagation; retained hashes unchanged | Active main/worktree callers, retained-input evaluation and adoption evidence |
| SAR | Bounded split replay, frozen membership preview, isolated queue coverage/binding tests | Actual extraction error decision, coverage integration and bounded scientific adoption |
| SST | Full frozen-matchup reassessment matches retained baseline; synthetic root propagation check | Actual retained-preparation selection and active caller adoption |

No project has been declared fully scientifically migrated by this table.
