# Workflow draft and corrective record milestone

2026-10-06. Isolated `workflow/execution-acceptance` branch. Draft commit 66c3492;
record/future-input patch 7edb3a8; executor outcome follow-up d587889.

Review [workflow guidelines](../../docs/workflow_guidelines.md),
[Slurm submission proposal](../../docs/slurm_submission_workflow.md) and
[M0–M5 migration plan](../../docs/slimmer_core_migration.md).
Executable [examples](../../examples/slimmer_workflows/README.md) cover root producer
bindings, distinct track/arm/run stage directories, bulk file manifests and coverage,
ordered stages in one allocation, and CPU/GPU/CPU jobs with IDs and a launch ledger.
@ variants, checkpoint continuation and frozen reassessment are documented patterns.

Validation: **202 compatibility cases pass** at 7edb3a8 (292.18 seconds), then
**33 focused cases pass** for d587889 (56.16 seconds). These overlap; do not add their
counts as unique tests. Five workflow and nine record regression cases cover actual
local computations and fake scheduler launches; no live jobs or production changes.
[JUnit compatibility](compatibility.xml), [follow-up](outcomes-followup.xml) and
[environment/module inventory](validation.json) retain the evidence.
This is not a full-suite rerun. Earlier evolving-tree trials included a source-drift
cache failure and an invalid synthetic DB fixture; final runs held source stable and
used a real authoritative task-record fixture.

The record corrections reject repeated resolved save_dir within a composite item
before queue/backend construction, collect existing terminal outcomes by requested
task ID across tags, reject active rows owned by another tag transactionally, validate
retained output receipts and require readable authoritative records for cache hits.
The executor boolean also preserves failed/interrupted outcomes under earlier tags.
No task hash or record schema changes were introduced.

The future-producer example exposed controller reads/hashes of nonexistent promised
data. With after, data/prevs stay on the task and are recorded by the consumer worker;
repository discovery reads code metadata independently. The acceptance queues all
three launches before running any payload, then verifies exact producer paths, data
hashes and lineage after dependency-ordered local worker execution.

M1 remains open for data-identity quality and pre-submit destination/force guards,
including active/held/prepared work. M2 still owes automatic run_lock lineage and
existing-producer value/identity binding/change policy. Preserve input records/products
unchanged in the current explicit-binding recipes. Consumer migration and API removal
remain later phases.

Slurm direction: retain profiles and afterok/--after; --hold already fits a profile
directive. --dry-run remains a side-effect-free placeholder preview. A runnable
prepare-without-submit bundle plus optional submission/ID-recording helper is proposed,
not implemented. Claims, actual scheduler arguments and manual-launch uncertainty
must be addressed before adoption; there is no new DAG or all-sbatch-flags API.
