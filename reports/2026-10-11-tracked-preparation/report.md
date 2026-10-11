# Tracked preparation and worker source costs

Isolated FlexLock 0.9.0 checkout, branch `workflow/execution-acceptance`.
Source grouping: `e6dec34` with corrected composite fixture at `ff7b2c4`.
Hash-only fingerprint capture: `dbfb288`. Final benchmark harness: `f5f5156`.
Production installations and scientific project dependencies are unchanged.

Two internal redundancies were removed, preserving public signatures, queue
payloads, fingerprint values and provenance fields:

- Controller repository collection groups literal source settings independently
  of per-item data/prevs paths. Settings containing interpolation retain the old
  full-snapshot grouping, since they may depend on omitted inputs. Distinct source
  settings, inherited defaults and composite stages remain supported.
- Fingerprinting captures a fresh Git tree without computing the unused dirty
  flag. Public `create_shadow_tree` and provenance snapshots still report dirty
  status. No tree is cached; staged/modified/deleted/untracked content and existing
  include/exclude behavior remain part of fingerprinting.

## Measurements

Three alternating pairs per fixture, fresh processes sequentially on
compute-116-7 with 16 affinity CPUs. Serial compilation, two existing metadata I/O workers. Source and
per-item data tracking enabled; automatic cache discovery disabled. Preparations
use a mocked scheduler; local runs execute only the tiny synthetic hash workload.
Inputs are 1,000 distinct 4 KiB files. Runtime source stayed frozen at `f5f5156`.

| Median | Baseline | Current |
| --- | ---: | ---: |
| 1,000-item preparation | 18.153 s | 16.924 s |
| Controller repository collection | 1.915 s / 1,000 merges | 0.054 s / one merge |
| 100 tracked local items, including preparation | 55.556 s | 35.150 s |
| Fingerprint source-tree work, 100 captures | 30.480 s | 9.769 s |
| Git status, master plus items | 101 calls / 20.825 s | one call / 0.187 s |

Preparation improves 6.8% at the median, with a retained regression in pair 1:
17.244 s current versus 15.050 s baseline. Source collection itself improves in
every pair. All three local worker pairs improve; the median reduction is 36.7%.
Nested Git-status time is included in source-tree time; do not add them together.
These are local synthetic measurements, not guarantees for every filesystem or
scientific workload. Remaining fresh tree captures cost about 9.8 s per 100 items;
they were not amortized across possibly changing source.

The initial phase diagnosis found source-only repository collection at 0.022 s
versus source/data collection at 1.851 s, and 1,001 versus 2,000 config merges.
The source/data master snapshot itself took 0.546 s; SQLite writes took 0.069 s.
That single instrumented sample supports diagnosis, not a stable provenance
overhead comparison. Metadata waits remain substantial and variable.

## Verification and isolation

[Source checks](source-tests.xml): 98 passes. Hash equivalence covers staged,
modified, deleted and untracked files with full/include/exclude scopes. Hash-only
capture preserves the real index bytes, HEAD and refs. The historical status
check can refresh index stat metadata, so its check compares staged content rather
than demanding unchanged index bytes. An initial overly strict assertion and an
incorrect partial-task fixture were corrected before final acceptance.

[Validated runs](validation.json): six equivalent prepared queues / 6,000 configs,
plus six local queues / 600 independently verified products. Source trees match
within each matrix; all local fingerprints match. Master and every item retain
the expected xxh64 input hash, canonical input path, source tree and completion
receipt. No unexpected code drift. Cache DB contents confirm independent cold
case caches, with one input during preparation and 100 inputs during execution.
The existing mtime-cache policy is unchanged.

The timing drivers originally imported runtime modules before selecting the
scratch hash cache. Those superseded preparation pairs and the interrupted worker
matrix are retained under `2026-10-11-source-grouping` and
`2026-10-11-fingerprint-status`; they are excluded from final acceptance. Final
drivers isolate before import, using a sibling cache directory to avoid creating
the output directory before the measured driver. Prepared artifact count remains
2,007; sibling hash-cache files are outside this count. Ten tracked local items
were also profiled initially; that instrumented timing is diagnostic only.

The [SST consumer check](consumer-validation.json) reads the existing frozen
reassessment's SHA256/schema/coverage contracts, binds the callable signature and
prepares its unchanged config in a fresh scratch queue. Original artifact hashes
are unchanged. No scientific callable, source snapshot or scheduler submission
runs in this check; it is config/guard/queue/reader acceptance, not scientific replay.

An additional worker/receipt check initially launched the older installed
FlexLock from the rendered Slurm bootstrap: the queue recorded failure but the
old worker returned zero. The test fixture now selects this checkout explicitly
through child `PYTHONPATH`; production backend environment precedence is unchanged.
The final worker test results are retained separately in `worker-tests.xml`:
72 passes, giving 170 distinct focused passes across the two suites. Initial
worker results are retained in `worker-tests-initial.xml`; no full-suite claim.

## Evidence and next boundary

[All acceptance repetitions](summary.json), [phase diagnosis](diagnostic-manifest.json),
[analysis](analyze.py), [consumer probe](consumer.py), [preparation pairs](paired_matrix.py),
[worker pairs](worker_matrix.py). Raw acceptance folders:

- `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-11-source-grouping-isolated`
- `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-11-fingerprint-status-isolated`

The [nested-pointer experiment](../2026-10-11-nested-pointer-prototype/report.md)
provides the next concrete compatibility decision. Default writers still emit
every pointer. Automatic cache discovery retirement, optional fingerprint/index
policy and larger ownership-cache working sets remain separate migration work.
