# Independent-review follow-up: lineage, input identity and destination guards

2026-10-06. Isolated workflow/execution-acceptance branch. Lineage/coverage commit
23fb142; guards/workflow commit 3d86340. Production dependencies and scientific
outputs were not changed; no scheduler jobs were submitted.

The [independent review](/ontap/user/qfebvre/workflow-proposal-2026-10-02/plans/details/flexlock-independent-review-2026-10-06.md)
is addressed without adding a DAG, artifact class hierarchy or prepared-launch manager.

## Implemented

- Lineage deduplicates canonical producer paths. Two prepare/train runs with the
  same basename both survive; unique-name keys retain their existing shape.
  Flattening preserves same-named branches, aliases and shared ancestors and
  terminates historical cycles.
- File processing verifies the frozen manifest SHA256 and parses the same bytes.
  Coverage checks recorded and product input identities. Restoring an input after
  processing different bytes cannot satisfy the gate. Checking current input files
  is a separate --check-current-inputs option.
- Project controllers hold POSIX destination/queue locks during preflight,
  mutation and dispatch. Pending/running queue rows reserve products before worker
  records exist, including products outside the queue root and held submissions.
  Force/overwrite/unsafe cannot bypass these rows. A new controller cannot append
  to an active queue root and replace its master provenance. Batch refusal happens
  before old completion/results are removed. Cleanup retains the locked inode.
- Force dry-run leaves records/markers unchanged, including sweeps. The shared-root
  sweep force reset now targets the same queue directory as actual execution.
  Old cache-index fingerprints are rejected when the replacement record stores a
  different fingerprint. A forced
  HPC-to-local replacement removes stale worker references. Single queued failed/
  interrupted outcomes are collected accurately rather than labelled SUCCESS.
  Local callables without save_dir still create no output directory.
- The project acceptance helper checks selected producer completion and declared
  output integrity. Standalone producers require a done queue row; preceding
  composite stages use their own authoritative record and completion evidence.
  run_lock remains a generic record reader. Real schema/scientific compatibility
  checks stay project-owned.

Review [workflow guidelines](../../docs/workflow_guidelines.md),
[Slurm direction](../../docs/slurm_submission_workflow.md) and
[migration plan](../../docs/slimmer_core_migration.md).
Slurm preparation is reduced to a future backend materialization seam returning
real payload/script paths and submission argv. Managed claims/attach/dispose/recovery
and a public prepared-launch lifecycle are deferred. Existing profiles, --after,
--print-job-id and profile-based --hold remain.

## Validation

**249 selected compatibility cases passed** in 179.26 seconds. A final small
no-save_dir guard correction then passed **35 focused API/guard cases** in 16.64
seconds. The sets overlap: 250 distinct cases, not 284 or a full-suite result.
[Compatibility JUnit](compatibility.xml), [follow-up JUnit](followup.xml),
[source/environment inventory](validation.json).

Selection covers destination/save-dir guards, example workflows, reviewed record
contracts, root-anchor CLI sweeps, sweep semantics, pipelines, parallel workers,
Slurm validation/dependencies, lineage/loading/snapshots, API, index and task records.
Tests include local computations, spawned workers and fake scheduler calls.
Tracked source was held stable during each run. Earlier trials corrected the
helper's mistaken whole-composite completion requirement and two mock fixtures
that created pending queues before controller preflight.

## Scope and remaining work

Locks require cooperating controllers and a filesystem supporting flock. Direct
ParallelExecutor/queue mutation remains advanced one-controller use. Queue guards
track pending/running tasks, not the entire scheduler allocation lifetime. Stop old
pool workers before forced reuse; completed rows alone do not establish pool exit.
Failed/ambiguous submission can leave reserved pending rows: inspect scheduler and
queue state before explicit maintenance. There is no automatic expiry/takeover.

Force replaces current evidence without archiving it; preserve records or use a
fresh path when downstream historical references matter. External edits to products
cannot be prevented by controller locks. The orchestration example ledger remains
best-effort and documents the acceptance-to-ID-write crash window.

M1 directory identity remains open. M2 still owes automatic direct run_lock lineage
and existing-producer value/identity binding/change policy. M3 optional policy/caller
inventory, M4 measured thousand-item overhead and M5 adoption remain later work.
Benchmark config/queue serialization, destination metadata, source capture, input
hashing and scheduler calls separately; smart_run=False still captures provenance.
No scalability or prepared-submission guarantee is inferred from correctness tests.
