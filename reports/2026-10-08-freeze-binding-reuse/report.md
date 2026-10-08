# Sweep freezing and binding reuse — 2026-10-08

Cache-off preparation for 1,000 items now takes a **20.209s median**, down from
**23.315s** after the first optimization (13.3%, three repeats per revision).
Against today's original 30.807s baseline, the two slices together reduce the
median by **34.4%**. Twenty seconds and 2,007 files still warrant further work.
Runtime commits are **64c2d9d** (detached-copy reuse) and **a32d227** (conservative
post-freeze shortcut), on the isolated validation branch. Production installs
are unchanged.

## What changed

The sweep compiler uses a private combined freeze/bind helper. Freezing still
makes a detached copy and resolves aliases, relative references, resolver
arguments and custom resolver results. Binding then uses that detached copy,
rather than constructing an identical second working config. Public functions
retain their copy semantics; queue formats and CLI/sweep-file usage are unchanged.

After full freezing, a recursive plain-container scan checks for remaining `${`
syntax. If there is none, the item has no remaining interpolation to bind and the
compiler returns its owned frozen config. Otherwise the full binding pass runs,
including producer reads, active-queue guards, latest selection, defaults, recorded
producer identity and future-path handling. Escaped syntax conservatively takes
the ordinary path. This is not a scan of the original config: a custom resolver
can reveal a producer read only during freezing, and the new regression test
checks that its selected record remains bound and detects later replacement.

Removing the initial detachment would change how structured/read-only configs
behave, so that copy remains. Required checks still precede dispatch; no async
checks or new public execution mode were introduced.

## Measurements

Same Python/dependencies, NFS host, fixture files and mocked scheduler harness as
[the first slice](../2026-10-08-preparation-reuse/report.md): 1,000 4 KiB files,
cache off, directory task records, four workers in one `0-3` array, one mocked
scheduler call. Framework imports precede the timer. Each revision remained
frozen during its sequential measurements; no real jobs were submitted.

| 1,000 items | Repeat 1 | Repeat 2 | Repeat 3 | Median |
|---|---:|---:|---:|---:|
| First-slice baseline, 0629889 | 24.394s | 23.315s | 20.624s | 23.315s |
| Copy reuse only, 64c2d9d | 22.883s | 21.583s | 22.103s | 22.103s |
| Copy reuse + post-freeze shortcut, a32d227 | 18.322s | 20.209s | 21.232s | 20.209s |

Copy reuse alone showed a 5.2% median reduction. The final reduction is larger,
but ranges overlap and measurements were grouped rather than interleaved; host
load varied. These are bounded measurements, not universal speedup guarantees.
Peak RSS medians are **141,756 → 142,788 KiB** (+1.0 MiB). Artifact count remains
**2,007**, with unchanged scientific tasks and output destinations apart from each
case's prefix.

The 100-item profile shows **404 → 204 OmegaConf creations**. Merges remain 201.
For this producer-free fixture, binding passes fall from 100 to zero; configs
containing live interpolation still run binding. Profiled elapsed time is 4.667s
(previous slice 6.979s), but profiler overhead and overlapping cumulative timings
make the unprofiled table the speed evidence.

Explicit source-tracked preparation: **23.175s**, one 1,000-item sample. The
retained controller lock declares the same filtered `benchmarks` source scope;
its snapshot identity is distinct from the full checkout HEAD. This does not
measure the much larger tracked worker/module-drift costs. Local smoke execution:
**9.244s**, 100 completed items, with all product IDs and input SHA-256 values
independently verified. No local worker speedup is claimed from this smoke sample.

## Correctness and retained failures

**198 focused tests passed in one final run** (129.58s), covering sweep/root
interpolation, swaps, presets/run references, chained futures, producer replacement
and disappearance, collision guards and pipeline execution. Fourteen new cases
cover equivalence to the old two-pass implementation, caller immutability and
read-only flags, container aliases, producer literal values, defaults, future
paths, latest selection, custom-resolver reads and the plain-config shortcut.

The initial copy-reuse run had 184 existing passes and 12 new fixture failures.
All failures occurred while computing the expected result with the old two-pass
path: a plain escaped literal loses its escape during freezing and the subsequent
pass interprets it again. The new fixture was corrected to ordinary text; producer
returned literals remain tested. The corrected 12 cases passed, then the full
198-case final suite passed. Initial evidence remains retained. The escaped-literal
issue in the old path is not fixed by this optimization and remains follow-up work.

All six before/final queue payloads match by item after normalizing only each
case output prefix. Each contains 1,000 pending items, one task pickle and one
array script, with no executed products. Different output paths imply different
task hashes; raw hashes are not expected to match.

Evidence: [summary](summary.json), [validation](validation.json),
[before manifest](before-manifest.json), [copy-only manifest](intermediate-manifest.json),
[final manifest](after-manifest.json), [source manifest](source-manifest.json),
[profile counts](profiles.json), [initial tests](initial.xml),
[corrected fixture tests](new-cases-recheck.xml), [final tests](final-tests.xml),
[source lock](source-controller-lock.yaml), [source hashes](source-evidence.json).
[analyze.py](analyze.py) reproduces queue/product comparisons and report data.
Raw artifacts remain under `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-prep-*`.

## Next target

The new 100-item profile shows `list_task_records` called twice (1.004 cumulative
seconds), 201 merges (1.067s), freezing (0.946s), and YAML queue serialization
(0.346s). These timings overlap and are profiled. Inspect the two queue reads,
row materialization and result collection after nonblocking submission before
choosing the next optimization; add unprofiled phase timings if attribution matters.
Preserve tag membership, historical records, append/resume guards and typed results.

Pointer/file consolidation and repeated tracked-worker source checks remain
separate tasks. Automatic cache discovery deprecation remains outside this pass.
Fix the demonstrated escaped-literal limitation separately with a compatibility
regression before broad adoption. No real scheduler, multi-worker contention,
scientific adoption or acceptable scaling claim follows from these measurements.
