# Existing producer bindings before dispatch

2026-10-07. Isolated workflow/execution-acceptance branch. Implementation 82b09a9;
preceded by directory identity correction 8f07e3e.
[Decision](../../docs/provenance_discovery_decision.md),
[guidelines](../../docs/workflow_guidelines.md),
[migration plan](../../docs/slimmer_core_migration.md).

Existing concrete run_lock reads bind before Project queued dispatch: single HPC,
sweeps, isolated workers and ordered pipelines. Each canonical producer is read once
per item resolution; values, record SHA256 and captured lineage travel together.
At stage start the worker rejects any full materialized record digest change or
absence before calling user code. Failure is recorded in the queue/error evidence
and does not produce a completion marker. Consumer force does not waive validation.
Optional defaults bind immediately; absent-to-present producer transitions are
changes too. Missing required fields in an existing inactive record fail before dispatch.
Literal interpolation syntax in returned strings/native containers remains literal.

Missing concrete producers paired with after, and paths of earlier ordered stages,
remain promised reads until stage start. Active queue reservations distinguish a
pending/running producer from its controller placeholder record under after. Without
a dependency, an active selected producer is rejected before consumer dispatch.
A pending sibling in the same queue does not make a completed selected producer
future work. The read is still of the exact selected producer, never a newer sibling.
latest selection is fixed at actual dispatch, including nested run_lock selection.
Exporting with --enqueue does not constitute dispatch.

## Validation

The broad trial had **361 passed, one future-chain regression and one existing
expected failure** in 223.07 seconds. That regression showed the queued producer's
controller placeholder must be deferred based on its pending/running reservation.
After correction, the 186-case follow-up had **174 passed and 12 test-fixture
failures**: newly added error inspection passed a string to get_all_tasks, which
requires a Path. Actual worker rejection/failure assertions had already succeeded.

After correcting that fixture, **72 affected checks passed** in 23.46 seconds;
**31 binding checks passed** in 3.22 seconds, including two added isolated-worker
and direct ordered-stage cases. Sets overlap: **366 distinct selected cases passed**,
one existing expected failure. This is not a full-suite claim. The broad and corrective
trial XML preserve their actual failures; final checks verify their corrections.
[Broad trial](compatibility-trial.xml), [corrective trial](corrective-trial.xml),
[final affected checks](final.xml), [isolated/chain checks](isolated-and-chain.xml),
[source/environment inventory](validation.json).

Coverage includes config/resolvers, discovery/snapshots, workflow examples, destination
and record guards, API/worker outcomes, dir/DB producers, root sweeps, scheduler
dependencies, index/cache compatibility, parallel/composite tasks, presets and data
hashing. Source stayed fixed during each run. Local/spawned workers and fake scheduler
calls only; no live jobs or production upgrade.

## Scope and next work

This is a stage-start record identity check, not a producer reservation or atomic
filesystem snapshot. It cannot prevent mutation after verification. Product content
identity and project acceptance remain separate: an unchanged record alone does not
prove unchanged bytes, success or scientific usability. Review a changed producer
before resubmitting, preferably using a fresh path.

Legacy unpinned run references under after remain advanced worker-time compatibility
behavior outside the supported concrete-producer recipe. Standalone readers and
low-level executor callers retain their resolution roles; the binding contract is
implemented on Project submission paths. Optional cache/resume semantics and historical
record readers remain. M3 caller/optional-policy inventory is next, followed by M4
thousand-item config/queue/source/data/binding overhead and M5 isolated adoption.
