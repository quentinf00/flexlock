# Reuse compiled sweep items during executor preparation

The isolated checkout implements the optimization at **1244e70**. Matched fresh
1,000-item preparation medians fall from **17.031s to 14.128s** for plain configs
(17.0%) and **26.560s to 23.447s** for producer-bearing configs (11.7%). Reuse is
faster in every corresponding large-sweep repeat. Process compilation remains
disabled; this improvement removes work in the controller.

## Change and safety boundary

`Project._submit_sweep` already merges, freezes and binds each item. It now marks
those items through a private executor keyword, `_compiled_tasks`, so preparation
guards can inspect the existing configs instead of merging them with the campaign
wrapper again. The wrapper only carries `save_dir` and `_snapshot_`.

The optimization requires that minimal wrapper, a root task target, an actual
`DictConfig` with its own `save_dir`, and an item from the current request. Custom
wrapper defaults, missing task destinations, plain dictionaries and non-root
targets retain merging. Ordinary low-level callers retain their original behavior;
`task_target=None` alone does not indicate a complete config. Historical completed
rows not in the request still merge and still participate in collision checks.

Only the two preparation guard passes reuse these items. Queue payloads, task
hashing, controller provenance, worker-side merges, source snapshots, selected
producer bindings and stage-start checks remain unchanged. Guard inspection does
not mutate the original configs. There is no new public CLI switch or execution
backend. Required destination/ownership checks still precede dispatch.

## Matched comparison

Frozen runtime **1244e70**, `compute-118-39`, 16 affinity CPUs, Python 3.11.14 and
OmegaConf 2.3.1. Three alternating baseline/candidate pairs per config fixture,
fresh subprocesses/output directories, sequential workloads, no concurrent tests
or source edits. All cases force serial compilation and retain the accepted
two-worker metadata I/O path. Automatic cache discovery is off. Scheduler calls
are mocked; no real Slurm jobs or scientific inputs changed.

The baseline overrides only the private constructor hint to false on the same
revision, reproducing the existing per-item guard merge. The candidate uses the
hint supplied by `Project`. Both use the same compilation, queue, source, guard
and submission code. The retained driver counts calls at the compiler and executor
call sites; worker aliases are not counted by this instrumentation.

| Config | Guard path | Repeat 1 | Repeat 2 | Repeat 3 | Total median | Executor median |
|---|---|---:|---:|---:|---:|---:|
| Plain | Merge again | 17.412s | 16.987s | 17.031s | 17.031s | 6.214s |
| Plain | Reuse | 14.641s | 11.776s | 14.128s | 14.128s | 3.979s |
| Producer reads | Merge again | 28.329s | 25.629s | 26.560s | 26.560s | 8.336s |
| Producer reads | Reuse | 23.447s | 23.917s | 22.950s | 23.447s | 5.575s |

Every large case makes 1,000 compiler merges. Executor preparation falls from
**1,000 merges to zero**, with one other controller merge retained. Median peak
RSS falls about 30MiB for plain configs and 45MiB for producer-bearing configs.
Full preparation includes the remaining config work, destination checks,
reservation writes, queue serialization, source handling and mocked submission.
Executor timing is nested within total time; do not add them.

This is acceptance on one shared NFS host, not a universal speed guarantee.
Earlier timing series used different host conditions and cannot be combined into
an exact cumulative speedup. The single 100-item preparation pair takes
**1.591s baseline / 2.188s reuse**, so it does not demonstrate a small-sweep gain.
Fewer merges are verified at that size too; no size threshold is justified by
one noisy elapsed-time pair. Files remain **2,007 per 1,000-item submission**.

## Correctness and provenance verification

Focused preparation/compiler tests: **61 passes, two expected skips**. Broader
submission/binding/path/collision tests including the new API regression:
**108 passes**. Removing overlap yields **161 distinct passes, two skips**.

New cases verify direct frozen guard inputs against the old merge path, exact
queue payloads, unchanged caller configs and reservations, shared output roots,
historical-row collision rejection, fallback for partial/custom wrapper contexts,
and the actual `Project` call path. The latter makes one compiler merge per item
and no second preparation merge. Existing binding/chaining and overwrite guards
remain covered. This is focused acceptance, not a full-suite claim.

Independent analysis compares **16 prepared queues / 14,200 configs**, normalizing
only the output-case prefix. It checks all serialized fields, ordering, pending
counts, one mocked scheduler call, one pickle and one four-worker script per
submission, and absence of scientific products during preparation. Producer
digests/read records remain part of the config comparison. Local execution takes
9.527s in one 100-item sample; all 100 output hashes match the actual input bytes.
That is a local execution check, not another preparation speed claim.

Source-aware preparation takes **19.121s baseline / 16.642s reuse** in one pair.
Both source records retain the same source tree, parent revision, environment
hashes, discovery information and config. Their generated shadow commit IDs
differ because Git commit timestamps differ; an initial overly strict record
comparison caught this expected distinction. The analysis verifies both commit
objects' trees and parents before excluding generated IDs from semantic equality,
and retains both original records and commit contents. No source or upstream
identity check in the library was loosened.

## Follow-up

The controller avoids a proven redundant merge without introducing another
parallel execution mechanism. Remaining preparation work includes OmegaConf
compilation, queue serialization and metadata I/O. Next inspect pointer/marker
bookkeeping and remaining phase costs before choosing another optimization;
retain durable lock inodes, ownership checks and historical readers. Tracked
worker source checks, automatic discovery retirement and the known escaped-literal
bug remain separate outstanding items. This checkpoint does not deploy changes
to production installations or certify real research workflows.

Evidence: [manifest](manifest.json), [summary](summary.json),
[validation](validation.json), [guard tests](guard-tests.xml),
[submission tests](submission-tests.xml), [baseline source record](source-baseline-controller-lock.yaml),
[reuse source record](source-reuse-controller-lock.yaml), [commit contents](source-commits.json),
[case driver](case.py), [matrix driver](matrix.py), [analysis](analyze.py).
The case driver reuses the retained
[full preparation driver](../2026-10-08-process-preparation/case.py).
Raw logs/artifacts remain under
`/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-compiled-guard-reuse`.
