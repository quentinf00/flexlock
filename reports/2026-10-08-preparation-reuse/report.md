# Preparation reuse — first optimization slice, 2026-10-08

Reusing effective executor configs across its two guard passes reduced the median
cache-off preparation time for 1,000 items from **30.807s to 23.315s (24.3%)**.
This is a useful first reduction; 23 seconds and 2,007 files remain too expensive
for tiny tasks. The runtime change is committed at **0629889**, on the isolated
`workflow/execution-acceptance` branch. Production installations are not updated.

## Change and preserved behavior

`ParallelExecutor` now merges each item with master defaults once and reuses the
result for shared-output checks and destination reservations. Shared-root analysis
reads a plain unresolved stage container, constructing a detached OmegaConf stage
only when shared-output contracts need resolution. The remaining executor merge
is necessary for low-level callers supplying partial overrides, including callers
with `task_target=None`. Queue payloads, public arguments and worker formats are
unchanged. Historical completed rows still participate in collision checks.

Five new regression cases cover partial overrides at three target paths, inherited
output contracts, caller config immutability, detached stage-root interpolation,
and collision checking against completed rows before new queue insertion.

## Measurements

All preparation measurements use mocked scheduler calls, four workers in one
array (`0-3`), cache off, directory task records and the same 1,000 deterministic
4 KiB input files. Python and dependency imports precede the timer. Runs were
sequential on NFS4 home storage, host `compute-118-39`. Each revision remained
frozen throughout its measurements. There is no real Slurm submission here.

| 1,000 items | Repeat 1 | Repeat 2 | Repeat 3 | Median |
|---|---:|---:|---:|---:|
| Before, 1de71ff | 30.807s | 30.269s | 36.112s | 30.807s |
| After, 0629889 | 24.394s | 23.315s | 20.624s | 23.315s |

The before/after ranges do not overlap in this sample. Runs were grouped by
revision rather than interleaved, and host load varied; three repeats do not
establish a universal speedup. Peak RSS increased from a median **134,488 KiB**
to **141,756 KiB**, about **7.1 MiB**, because effective configs remain available
through preparation. File count stayed **2,007** in every case.

The separate 100-item cProfile comparison shows:

| Call | Earlier before profile | After profile |
|---|---:|---:|
| `merge_task_into_cfg` | 301 | 201 |
| `OmegaConf.create` | 504 | 404 |
| `bind_existing_run_locks` | 100 | 100 |

These counts compare the retained October 7 baseline profile with this slice.
The profiled elapsed time increased from 6.545s to 6.979s despite lower counts;
profiler overhead and host conditions make it unsuitable as a speedup estimate.
Cumulative function times overlap. The fresh unprofiled table is the timing evidence.

An additional 1,000-item preparation with explicit source tracking took **31.500s**
(one sample). The source declaration includes `benchmarks`; its filtered snapshot
identity differs from the checkout HEAD by design. The raw lock is retained and
records explicit discovery, repository identity and environment hash. This is
controller preparation, not the expensive tracked worker execution benchmark.
A 100-item local smoke run took **9.087s**, completed all items, and all product
IDs and SHA-256 values match their input files independently.

## Validation and test corrections

All six before/after queues contain 1,000 pending items with equal parsed task
payloads after replacing only each case's output-directory prefix. Raw task hashes
naturally differ because destinations differ. Each case has one pickle, one Slurm
script and one mocked scheduler call, with no scientific products executed.

**183 distinct selected test cases pass across the initial run and follow-ups.**
The initial run had 179 passes and four failures; its XML is retained. Two cache
cases pass when the accidentally shared global test index is removed. Two guard
assertions expected unexecuted directories not to exist; both failures were
reproduced with the unchanged baseline module. Their corrected assertions allow
reservation bookkeeping while checking that no user products or success receipts
exist. Both corrected cases pass, including downstream failure/resume behavior.
This is focused acceptance, not a full-suite claim.

Evidence: [validation](validation.json), [summary](summary.json),
[raw before manifest](before-manifest.json), [raw after manifest](after-manifest.json),
[source manifest](source-manifest.json), [profile counts](profiles.json),
[initial tests](initial.xml), [isolated cache recheck](cache-recheck.xml),
[baseline failure reproduction](baseline-guard-reproduction.xml),
[corrected guard recheck](guard-recheck.xml).
Manifests contain exact commands, revisions, dependency versions, load averages
and process output. Raw directories remain under
`/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-prep-*`.
[analyze.py](analyze.py) recomputes queue/product comparisons and report data.

## Next slice

Reduce reconstruction during freezing and producer binding, starting at call sites
where configs are already owned and frozen. Preserve argument interpolation,
indirect producer reads, latest/run selection, literal escaping and future `--after`
inputs. Do not infer that a config is complete from `task_target=None`, introduce a
new public execution mode, or move required guards after dispatch. Measure the
next slice against this frozen revision with the same fixtures and focused checks.

Pointer/file consolidation and repeated worker source/module checks remain separate
priorities. Automatic cache discovery removal remains a migration task outside
these measurements. Sweep-file semantics stay unchanged. This first improvement
does not establish acceptable scalability or scientific adoption.
