# Shared parent resolution during ownership scans

Runtime `da91f41`, compared with retained `7473b0f` guard behavior. Both variants already use the safe C YAML loader. Validation is isolated to this checkout; installed production code is unchanged. No actual Slurm jobs were submitted.

## Change and boundary

Within one ownership scan, destination paths now reuse the resolved parent directory. Each final component is still checked for a symlink; symlink targets receive full `Path.resolve()` treatment. Root and parent-traversal cases retain full resolution. The helper is used by selected-producer ownership and controller preflight, not by general queue serialization/reservation calls.

The parent map is local to one scan. Each new check rereads queue status and starts a new map, so parent/final symlink retargeting and task edits between checks remain visible. There is no persistent ownership answer, schema, writer or file-format change. As with existing filesystem/queue checks, this does not provide an atomic snapshot of concurrent mutations: a parent retargeted during a scan may be observed on the next scan rather than by later rows of the current scan. The reuse boundary is deliberately one scan, not a whole sweep or binding cohort.

This reduces repeated traversal of shared directory prefixes. It does not reduce the number of YAML rows scanned.

## Validation

**130 focused passes, two expected skips.** Added checks compare canonical results with `Path.resolve()` for absolute/relative paths, missing parents, dot/parent traversal, spaces, parent symlinks, final relative/absolute/dangling symlinks and loops. Parent resolution happens once per scan; a fresh scan sees parent retargeting. Existing final-symlink, status/task-edit, historical pipeline, ancestor ownership, malformed reservation, pre-submit collision and joined-I/O checks remain green.

Analysis verifies ten equivalent prepared queues / 10,000 configs (six primary and four follow-up), 6,000 completed bindings and 600 future bindings. Both variants reject the active-ancestor stale-artifact case and preserve exact allowed future paths. Files remain **2,007**.

## Matched measurements and uncertainty

Three alternating repetitions per fixture/variant, fresh processes sequentially on compute-118-39, runtime frozen at `da91f41`. Serial compilation, synthetic 1,000 × 4 KiB inputs, mocked scheduler. Binding timers exclude fixture setup and initial config construction but include binding transforms, queue ownership and record reads.

| Primary fixture | Old median | New median |
| --- | ---: | ---: |
| Full 1,000-item preparation | 10.960 s | 12.714 s |
| 1,000 completed-producer bindings | 9.918 s | 8.812 s |
| 100 future bindings / 1,000 pending rows | 2.600 s | 1.919 s |

The pending fixture improves **26.2%**. All new runs (1.781–2.090 s) beat all old runs (2.558–2.736 s). Today's baseline differs substantially from yesterday's measurements; do not combine percentages across those sessions. A 1,000-future-binding workload was not measured.

Preparation was slower in all three primary pairs. This concern prompted separate profiled preparation diagnostics and two additional alternating pairs, all retained. Compilation wall/CPU time in the primary cases stayed around 2.6 s. Preparation diagnostics perform no active-row destination resolution; the new scan-helper construction is negligible. Their totals are 21.908/22.310 s under instrumentation, with comparable compilation and general destination-extraction costs; file creation, flock and metadata-thread waits dominate the rest.

The two unprofiled follow-up pairs reverse the primary result: current 8.116/7.505 s, baseline 10.342/14.339 s. Keep these separate from the original matrix rather than selecting favorable repeats. Preparation timing is variable and no stable gain or regression is established. Completed-producer timing also overlaps and has no active rows to optimize. Acceptance is for the narrower pending-row improvement and preserved behavior, not a claimed general preparation speedup.

## Call-count evidence and next step

Matched diagnostic profiles each decode **49,600 rows**. Across the full fixture, `Path.resolve()` calls fall **51,002 → 1,502**. Destination extraction falls from 3.632 to 1.656 profiled seconds; YAML loading remains similar (1.601/1.553 s). These are instrumented diagnostics, not the benchmark timing table; the current future diagnostic overlapped evidence analysis, so use it for call distribution rather than a controlled wall-clock comparison.

Repeated row decoding/scanning remains. Next evaluate bounded reuse of immutable decoded row data or a simpler lookup path, preserving fresh status reads, symlink semantics, unknown-row refusal and historical fallbacks. Do not cache an ownership answer. Avoid a new persistent index unless evidence justifies its writer/compatibility cost. File reduction remains separately planned behind older-reader compatibility; stable mutex inodes remain necessary.

## Evidence

- [Tests](tests.xml), [validation](validation.json), [primary manifest](manifest.json), [medians/repetitions](summary.json), [separate preparation follow-up](prep-followup.json).
- [Diagnostic measurements](diagnostics.json), [old preparation profile](prep-profile-baseline.txt), [new preparation profile](prep-profile-current.txt), [old future profile](future-profile-baseline.txt), [new future profile](future-profile-current.txt).
- Drivers: [matrix](matrix.py), [cohort](cohort.py), [preparation](prep.py), [baseline](baseline_guard.py), [context](context.py), [analysis](analyze.py), [preparation diagnostic](prep_diagnostic.py), [follow-up](supplement.py).
- Raw cases and preparation profiles: `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-10-destination-resolution`. Future profiles: `/tmp/flexlock-destination-baseline.prof`, `/tmp/flexlock-destination-current.prof`.
