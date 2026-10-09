# Shared queue readers and ancestor ownership

Runtime commit: `8ad211c`. Validation is isolated to this checkout; installed production code is unchanged. No actual Slurm jobs were submitted.

The required-producer binding guard now detects active replacement work in a selected producer's own or ancestor queue, including when its explicit pointer refers to an older terminal queue. Previously, a pointerless nested producer could bind an old artifact while its replacement was pending. The retained counterexample reproduces that old behavior and verifies rejection with the new reader. An explicitly allowed future binding retains the selected path and captures no stale producer record. Optional/default resolver policy is unchanged.

`flexlock.queue_refs` centralizes pointer and marker reading, legacy relative marker paths and canonical database deduplication. Destination ownership checks inspect explicit locators and existing ancestor databases without directory discovery or file creation. An active row whose destination cannot be determined fails closed; an unrelated pending sibling with a known destination does not block a completed producer. Malformed reservation locators and missing pointer databases reject ownership checks. A missing legacy marker database still permits reading an archived standalone full lock. Artifact readers retain tolerant marker parsing.

Writers, file formats and durable mutex inodes are unchanged. Prepared file count remains 2,007. This fix does not make pointer omission safe for older installed readers; any writer migration still needs a compatibility plan.

## Verification

The focused final suite passed **166 tests with two expected skips**. After the final legacy reader edit, 72 overlapping reader/record tests passed again; these are not 72 additional distinct tests. Coverage includes current pointers, absolute/relative markers, ancestor ownership, all queue terminal states, stale pointers, unknown destinations, archived locks, malformed locators and exact future bindings. An initial relative-marker fixture used the wrong parent path; its two failures were corrected in the fixture and the original result is retained.

- [Final test results](final-tests.xml), [legacy recheck](legacy-tests.xml), [initial fixture errors](fixture-error.xml).
- [Validation assertions](validation.json): six equivalent prepared queues / 6,000 configs, 6,000 equivalent completed bindings and 600 equivalent future bindings, plus the stale-binding counterexample.

## Measurements

Three alternating baseline/current repetitions for each fixture ran in fresh processes, sequentially, on compute-118-39 with 16 affinity CPUs. Runtime source remained frozen at `8ad211c`; compilation was serial. Baseline ownership functions are retained from `d0062a7`. Valid marker reading is shared by both variants. The preparation fixture uses 1,000 synthetic 4 KiB inputs and mocked submission. Binding timers exclude fixture setup and initial config creation, but include binding's copy/transform, ownership and record reads.

| Fixture | Baseline median | Current median |
| --- | ---: | ---: |
| Full 1,000-item preparation | 13.373 s | 13.289 s |
| 1,000 completed-producer bindings | 10.161 s | 10.626 s |
| 100 future bindings from a 1,000-item pending queue | 12.863 s | 13.299 s |

Preparation shows no meaningful speed change given the observed variation. Stronger ownership adds about 0.464 s (4.6%) to the completed fixture and 0.436 s (3.4%) to the future fixture. The latter already costs roughly 13 seconds under the old implementation: repeated active-row YAML decoding and destination path scans are a separate bottleneck from ancestor probing. These are synthetic local measurements, not cluster scaling results; 1,000 future bindings were not timed.

Next profile and reduce repeated active-row decoding/path lookup while preserving exact destinations, mutable ownership and historical-row fallbacks. A global ownership cache would risk stale answers. Keep writer migration deferred until reader compatibility is established. Automatic cache discovery retirement remains planned, not implemented.

## Retained evidence

- [Manifest](manifest.json), [all repetitions and medians](summary.json).
- Drivers: [matrix](matrix.py), [preparation](prep.py), [binding cohorts](cohort.py), [baseline context](context.py), [original guard](baseline_guard.py), [analysis](analyze.py).
- Raw cases: `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-09-queue-reference-readers`.
