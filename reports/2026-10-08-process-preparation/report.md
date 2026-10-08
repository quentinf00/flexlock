# Opt-in process preparation: correctness passes, default adoption rejected

The bounded implementation is available in the isolated validation checkout at
**fd4428c**. It is deliberately **off by default**. Full-submission measurements
do not support enabling it automatically: gains depend on the config, and spawned
compilation has severe slow runs on this host. No production installation or real
Slurm job changed.

## Implementation and compatibility boundary

`Project._submit_sweep` delegates its existing merge, preset freeze, chained-path
validation and freeze/bind sequence to a private compiler. The serial sequence
is unchanged. Experimental `FLEXLOCK_PREP_PROCESSES=2` or `4` permits spawned
processes for at least 512 items, in batches of 50. These are experimental tuning
values, not established universal thresholds. Worker count is bounded by CPU
affinity, `SLURM_CPUS_PER_TASK` when present, and four. Child processes cannot
create a nested pool.

The pool transports **pickled OmegaConf configs**, including the original base,
rather than reconstructing the prototype's plain containers. Only canonical
primitive configs, ordinary references and the stock `run_lock` resolver are
eligible. Custom resolver calls, replaced `run_lock`, `run`/`latest`/`now` and
other named resolvers, structured configs (including nested ones), resolver
caches, attached configs, small sweeps and one-CPU allocations stay serial.
The follow-up guard also keeps interactive entry points serial. Eligible Python
scripts must guard their entry point with `if __name__ == '__main__'` as required
by spawn; this is another reason the experiment is not a transparent default.

All batches join before any queue writes, destination reservation or scheduler
call. A compilation/pool failure propagates, without a serial retry that might
rebind already-read producers after a change. Existing collision/ownership guards,
queue serialization, stage-start producer verification and source capture remain.
This is an experiment behind an environment switch, not a new supported CLI mode
or a framework for arbitrary user resolver initialization.

## Full preparation comparison

Frozen runtime **fd4428c**, `compute-118-39`, 16 affinity CPUs, Python 3.11.14,
OmegaConf 2.3.1. Three rotating repeats, fresh subprocesses and output directories,
sequential workloads, no concurrent tests or source edits. Existing two-worker
metadata I/O remains enabled in every case. Automatic cache search is off.
Scheduler calls are mocked; each 1,000-item case creates one four-worker array
script and one pickle. Timers include compilation, queue, guards, source handling
and mocked submission. The controller's normal task target is unchanged.

| Config | Processes | Repeat 1 | Repeat 2 | Repeat 3 | Total median | Compilation median |
|---|---:|---:|---:|---:|---:|---:|
| Plain | 1 | 21.889s | 18.491s | 19.413s | 19.413s | 4.926s |
| Plain | 2 | 20.841s | 23.664s | 22.406s | 22.406s | 3.223s |
| Plain | 4 | 16.842s | 16.717s | 27.634s | 16.842s | 2.671s |
| Producer reads | 1 | 28.019s | 34.664s | 28.393s | 28.393s | 12.694s |
| Producer reads | 2 | 23.844s | 29.458s | 24.363s | 24.363s | 6.990s |
| Producer reads | 4 | 33.331s | 94.644s | 186.817s | 94.644s | 76.449s |

Two processes reduce producer-bearing total median by about **14.2%**, but make
plain total median about **15.4% slower**, despite faster compilation. Four
processes improve the plain median about **13.2%**, but worsen its worst observed
run and fail badly on producer-bearing preparation. Three repeats on one shared
host do not establish population percentiles or universal performance. Do not
compare these medians directly with the earlier 15.249s I/O series as if host
conditions were identical.

Every 1,000-item submission still has **2,007 files**. Process compilation leaves
the executor's second merge, queue serialization, destination checks and pointer
writes intact. Controller peak RSS and child peak RSS are retained in the summary;
the controller's RSS alone does not represent total process-pool memory. Child
peak RSS from `RUSAGE_CHILDREN` is a maximum, not a sum of simultaneous workers.

## Slow-run investigation and acceptance decision

The earlier unexplained 45.140s producer compilation outlier reproduces and is
more severe here. Four-process producer compilation takes 14.942, 76.449 and
163.680 seconds, with aggregate child CPU times of 14.296, 14.742 and 14.186
seconds. The slow plain four-process compilation takes 16.196 seconds with
7.230 aggregate child CPU seconds. Controller compilation CPU is under 1.1s.

These observations identify substantial non-CPU elapsed delay in the pool path;
they do **not** distinguish process startup/imports, filesystem waits, scheduler
contention or transfer/shutdown delays. Aggregate CPU is not a per-worker trace.
The outlier's root cause remains unresolved. No claim that NFS or producer reads
alone cause it is justified. The fact that plain compilation also stalls rules
out explaining the entire problem solely by selected producer record reads.

Default adoption is rejected on this evidence. Keep serial preparation and the
accepted two-worker metadata I/O as defaults. Prefer reducing repeated controller
merges/config reconstruction next. If revisiting the experiment, add bounded
per-worker startup/batch/transfer diagnostics before further default tuning, and
include worst observed timing as well as medians in acceptance. Arbitrary resolver
support and larger pools are not priorities for the slimmer core.

## Verification

The focused compiler/preparation suites pass **66 tests with two expected skips**;
the submission/binding/path/collision suites pass **99 tests**. The subsequent
interactive-entry guard recheck passes **18 tests** (overlapping the earlier suite).
A target fixture initially
used `${item}` after moving the item under `stage`; it was corrected to
`${stage.item}`. That was an invalid fixture reference, not a process-only
resolution difference.

Actual spawned results equal serial results for ordinary configs, sweep targets,
existing producer records (including native containers and literal interpolation
text), future producer paths and flag behavior. Changing the selected producer
after compilation is rejected for every tested child-produced config. Parent-only
custom resolvers execute correctly through serial fallback. A compilation error
prevents queue directory creation in the submission-path regression.

Independent artifact analysis compares **18 queues / 18,000 configs**, normalizing
only each output-case prefix, including producer path prefixes. It verifies task
ordering, all serialized config fields, one mocked scheduler call, one pickle,
one four-worker script, and absence of scientific products during preparation.
Local checks verify SHA-256 values against actual input bytes for **612 products**:
100 through small-sweep serial fallback and 512 through actual two-process
compilation. The latter takes 47.343s including full local execution, and is not
a preparation-only speed claim. Small serial/opt-in preparations take 1.459/1.466s
and both select one compiler. Source-aware two-process preparation takes 19.699s
in one sample; the controller source tree/env record is retained. No tracked
scientific worker performance improvement is established by that sample.

Evidence: [manifest](manifest.json), [summary](summary.json),
[validation](validation.json), [compiler tests](compile-tests.xml),
[submission tests](submission-tests.xml), [local process execution](local-processes.json),
[interactive guard recheck](interactive-tests.xml),
[source controller lock](source-controller-lock.yaml), [case driver](case.py),
[matrix driver](matrix.py), [independent analysis](analyze.py).
Raw logs and artifacts are under
`/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-process-preparation`.
