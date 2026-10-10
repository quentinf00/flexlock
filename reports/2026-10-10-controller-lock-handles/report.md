# Bounded preparation of controller lock handles

Runtime `0cb765a`, compared with retained `8bff8b5` destination guard. Isolated checkout only; production installation unchanged. The [phase investigation](../2026-10-10-preparation-phases/report.md) identifies metadata preparation as substantial, with SQLite writes around 0.02 s and controller preflight around 2.4–2.5 s in its fixtures.

## Change

Two existing bounded I/O workers now prepare controller directories and open their durable mutex files. After all opens join, the controller acquires flocks sequentially in the same sorted canonical-path order as before. It retains ownership across preflight, mutations and submission. OmegaConf, queue writes and ownership decisions do not enter the pool.

Every successful handle is registered for cleanup, including those opened after another item fails. Required failures join the workers, close handles and prevent entry into the guard body. A lock collision also closes all prepared handles. Existing mutex inodes, pointers and record formats are unchanged.

One practical difference: all lock handles are prepared before the first flock attempt. A refused controller can therefore create more empty directories/mutex files than the previous sequential loop; no queue, provenance or product write happens before ownership succeeds. Peak handle count still corresponds to the guarded destination set, as in the successful old path. Existing two-worker I/O defaults remain in place; one/four-worker correctness is tested, but this benchmark accepts only the default two-worker setting.

## Acceptance

**142 focused passes, two expected skips.** Added tests verify sorted main-thread flock acquisition for 1/2/4 I/O workers, joined open failures, cleanup of all handles and collision cleanup. Existing inode preservation, competing-controller exclusion, pending/running refusal even with force, reservation failures, legacy queues, immutable-row cache and exact producer binding checks remain green. No full-suite claim.

Twelve equivalent prepared queues / **12,000 configs**, all with 1,000 pending rows and one mocked scheduler call. A separate 10-item local smoke reaches done for every row, produces complete receipts and independently verified input SHA256 products. Source/data tracking are off; this does not establish tracked-source, scientific-consumer or multi-worker cluster acceptance. No actual scheduler jobs ran.

## Paired measurements

Three alternating baseline/current repetitions for plain and completed-producer-bearing 1,000-item preparation, fresh processes sequentially on compute-118-39. Runtime frozen at `0cb765a`; serial compilation. Guard-only timing brackets entry and release in both variants, avoiding full-profile overhead.

| Median | Old | New | Reduction |
| --- | ---: | ---: | ---: |
| Plain full preparation | 10.468 s | 7.462 s | 28.7% |
| Producer-bearing full preparation | 16.546 s | 14.057 s | 15.0% |
| Plain controller preflight | 3.751 s | 1.285 s | 65.7% |
| Producer-bearing controller preflight | 3.747 s | 1.579 s | 57.9% |

Filesystem variability remains substantial. Plain pair 3 regresses (7.330 → 8.034 s), with essentially equal preflight; producer pair 1 regresses (15.739 → 17.551 s), including a 4.120 s new preflight outlier. All runs, including regressions, are retained. These medians support local default adoption, not a guarantee for every run or filesystem. Do not combine percentages with prior sessions. Lock release remains sequential and variable; this change targets handle preparation only.

File count is still **2,007**. This is a latency optimization, not a pointer/mutex merger. Next measure source/data-enabled representative preparation and validate a consumer before broad adoption. Revisit repeated task hashing/binding only against their measured cost; keep writer consolidation behind older-reader compatibility. Automatic cache discovery retirement remains planned, not implemented.

## Evidence

- [Tests](tests.xml), [validation](validation.json), [manifest](manifest.json), [all repetitions](summary.json), [local smoke](local-smoke.json).
- Drivers: [matrix](matrix.py), [preparation/guard timing](prep.py), [baseline](baseline_guard.py), [context](context.py), [analysis](analyze.py).
- Raw cases: `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-10-controller-lock-handles`.
