# Provenance discovery decision and implementation

2026-10-07. Isolated workflow/execution-acceptance branch, implementation 063f00d.
[Decision](../../docs/provenance_discovery_decision.md),
[guidelines](../../docs/workflow_guidelines.md),
[migration plan](../../docs/slimmer_core_migration.md).

The smaller core retains automatic provenance. Examples now track effective stage
arguments through relative _snapshot_.data references and omit redundant prevs.
Direct run_lock reads record canonical producer, requested field, returned value,
default usage and a SHA256 of the producer record read. One stage resolution reads
each canonical producer once; snapshot lineage uses that captured metadata even
if the record changes afterward. Capture state is scoped to the resolution and
transient buffers are excluded from persisted callable configuration.

Missing required records/fields fail before local output creation. Explicit defaults
are visible; missing producers receive no fabricated lineage. Directory and DB-backed
producers work, including symlinks with relative DB markers. Workers record known
references even with data-ancestor discovery disabled. Generic run_lock remains a
reader; record identity is not product identity or scientific acceptance.

_snapshot_.discover has boolean repos/prevs switches, enabled by default. An explicit
canonical checkout suppresses a duplicate unfiltered automatic alias. Explicit scopes
remain authoritative; discovery failure warns of absent inferred source evidence.
Lineage discovery evidence distinguishes run_lock, explicit declarations and weak
data_ancestor association. Source evidence records explicit versus target discovery,
including worker snapshots whose source metadata inherits from the controller.

Local binding moved before guard directory creation to keep legacy vinc references
consistent. Required-resolution failures propagate rather than retrying with a
partially resolved config. Existing submission/destination guards remain in effect.

## Validation

The broad trial had **272 passed, one test-fixture failure and one existing expected
failure** (221.53 seconds). The fixture expected “not found” but the missing-record
error correctly says “no run.lock found”; both missing-record and missing-field paths
raise the expected resolution exception. After correcting that assertion, refining
repository diagnostics and checking raw-reader canonical DB aliases, the focused
follow-up had **103 passed, one existing expected failure** (2.20 seconds).
The sets overlap: **273 distinct selected cases passed**, one expected failure; no
full-suite claim. [Trial JUnit](compatibility-trial.xml), [follow-up JUnit](followup.xml)
and [source/environment inventory](validation.json) preserve the actual results.

Coverage includes resolvers/deferred resolution, tracking utilities/snapshots,
workflow recipes, guards/API, directory/DB/shared-root task records, root-anchor
sweeps, scheduler dependencies, index, reviewed record regressions, parallel workers
and pipelines. New cases verify external products, coherent read/metadata pairing,
same-named producers, aliases, fallback/required fields, effective input overrides,
heuristic flags/labels, canonical repository scope and directory/DB-backed workers.
Code was held stable during each run. Local/spawned workers and fake scheduler calls
only; no live jobs, production upgrades or scientific outputs changed.

## Remaining scope

This is capture at stage resolution, not existing-producer value/identity freezing
before scheduler dispatch. M2 still owes that change policy. Producer output ownership
association needs unambiguous declared-output evidence; ancestor discovery currently
stays labelled inference. Automatic cache equivalence/resume policy is unchanged.
M1 directory-content identity, M3 caller/optional-policy inventory, M4 measured
thousand-item config/queue/source/hash/discovery costs and M5 adoption remain open.
