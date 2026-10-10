# Bounded reuse of immutable task-row paths

Runtime `be865f9`, compared with retained `0f9c2b1` destination guard. Both variants already use C safe YAML parsing and scan-local parent resolution. Isolated checkout only; installed production code is unchanged. Scheduler submission is mocked.

Ownership checks now memoize an immutable set of unresolved destination strings derived from exact task YAML. The process-local LRU key contains the full text and YAML loader identity. It holds at most 1,024 rows; documents longer than 4,096 characters bypass it. The text limit bounds retained input characters, not an exact byte/RSS limit: decoded strings and Python objects add overhead. Exceptions are not cached. Values cannot be mutated by callers.

Queue status and task text are reread from SQLite on every check. Changed text gets a new key; replaced databases are reopened read-only. Canonical paths, symlinks, current working directory, queue identities and ownership answers are never retained in this cache. Existing parent-resolution reuse remains bounded to one scan. No schema, writer, file-format, resolver API or default-process change.

## Acceptance

**137 focused passes, two expected skips.** New tests cover single decoding with fresh status transitions, database replacement, relative-path behavior after changing cwd, eviction/capacity, oversized-document bypass, immutable values, loader separation and repeated parse failures. Existing task-edit, parent/final symlink retarget, unknown-row refusal, historical pipeline, ancestor ownership and pre-submit controller/binding tests also pass.

Six equivalent prepared queues / 6,000 task configs, 6,000 completed bindings and 600 future bindings are verified. Both variants reject active-ancestor stale-artifact selection and retain exact future paths. Prepared files remain **2,007**.

## Measurements

Three alternating repetitions per fixture/variant, fresh processes sequentially on compute-118-39. Runtime frozen at `be865f9`; serial compilation, synthetic 1,000 × 4 KiB inputs, mocked scheduler. Binding timers exclude setup/initial config creation, include binding transformations, ownership and record reads. The cache is cleared immediately before each binding timer. A YAML load counter is installed in both variants during binding.

| Fixture | Old median | New median |
| --- | ---: | ---: |
| Full 1,000-item preparation | 12.639 s | 10.236 s |
| 1,000 completed-producer bindings | 10.145 s | 7.989 s |
| 100 future bindings / 1,000 pending rows | 3.111 s | 1.834 s |

The pending fixture improves **41.0%**: all new runs (1.531–2.034 s) beat all old runs (2.730–3.376 s). In every repetition, YAML loads fall **49,600 → 991**; the new cache has 48,609 hits and 991 retained entries. Each selected row's status and each destination's filesystem resolution remain fresh. Row visits are not eliminated; repeated parsing and extraction are.

Preparation and completed-producer fixtures have no active rows to reuse. Their ranges overlap and the wider preparation variability remains unresolved; do not attribute their apparent median gains to this cache. Peak RSS is retained in the manifest, without a memory-saving claim. These timings are synthetic local measurements, not cluster scaling results. Do not combine percentages with earlier sessions whose baselines differ.

Benefits require repeated rows to fit the cache. Larger working sets can evict entries; oversized documents always decode again. Capacity/bypass behavior is tested, but large-cohort eviction throughput and a 1,000-future-binding workload were not measured. The bounded cache adds some lookup/extraction overhead on misses. No ownership-answer or global resolved-path cache is introduced.

## Next step and evidence

Return to full-preparation phase accounting: distinguish config construction/serialization from filesystem reservation writes and locking, then validate a representative consumer before expanding adoption. Remaining row visits are visible, but a persistent destination index would add writer/compatibility responsibilities; do not introduce it without stronger need. File reduction remains behind older-reader compatibility, with stable mutex inodes preserved. Automatic cache-discovery retirement remains planned, not implemented.

- [Tests](tests.xml), [validation and counts](validation.json), [manifest](manifest.json), [all timings](summary.json).
- Drivers: [matrix](matrix.py), [binding and counters](cohort.py), [preparation](prep.py), [baseline guard](baseline_guard.py), [context](context.py), [analysis](analyze.py).
- Raw cases: `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-10-ownership-row-reuse`.
