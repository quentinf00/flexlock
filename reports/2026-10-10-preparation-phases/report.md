# Full preparation phase accounting

Measurement revision `bc07c03`, before the lock-handle optimization. This investigation changes no runtime behavior. Sequential fresh processes on compute-118-39, serial compilation, mocked scheduler, synthetic 1,000 × 4 KiB inputs. Source/data tracking and automatic cache discovery are off. The producer fixture binds one synthetic completed producer across 1,000 configs; it is not the pending-cohort fixture.

The recorder times nested phases with wall clock and per-thread CPU. Inclusive time contains children; exclusive time subtracts instrumented children on the same thread. Main-thread exclusive wall totals are checked against total submission. I/O-worker durations are separate and must not be added to main-thread wall totals, since they overlap pool waits. Phase medians also need not sum to the median total.

## Findings

Three instrumented repetitions per fixture, plus one uninstrumented control each. Median instrumented total: plain 8.324 s, producer-bearing 14.037 s. Single controls are 10.230/14.524 s. Filesystem variation prevents deriving precise instrumentation overhead or a performance gain from those controls.

| Phase (inclusive median) | Plain | Producer-bearing |
| --- | ---: | ---: |
| Configuration compilation | 2.585 s | 6.723 s |
| Controller preflight | 2.409 s | 2.492 s |
| Product reservations | 1.179 s | 1.217 s |
| Queue YAML serialization | 0.530 s | 1.025 s |
| SQLite write transaction | 0.023 s | 0.024 s |
| Task hashing, 5,000 calls | 0.459 s | 0.931 s |
| Lock-handle release | 0.408 s | 0.477 s |

These rows overlap: hashing/serialization/SQLite are within executor setup; producer binding is within compilation. Producer binding alone takes 3.568 s, while config merging stays around 0.79 s. Five hashes per task are real repeated work but smaller than binding and metadata costs. SQLite inserts/commit are not the dominant metadata cost in this fresh-queue fixture; contention with live workers is unmeasured.

Most preflight exclusive time is spent preparing directory/lock handles and acquiring locks: about 2.10 s plain and 2.16 s producer-bearing, with only about 0.19 s main-thread CPU. Reservation workers likewise spend much of their time waiting for filesystem work. This supports bounded parallel handle preparation as the next small change, retaining sequential sorted flock acquisition rather than parallelizing ownership decisions or OmegaConf.

## Verification and limits

Eight equivalent queues / 8,000 configs, 1,000 pending rows and one mocked scheduler call per queue, serial compilation, 2,007 files. Main exclusive accounting, 5,000 hash calls, 1,000 YAML serializations, one write transaction and 1,000 reservation writes are asserted. The 10-item smoke checks the recorder separately; no scientific workload or actual Slurm job ran. Source capture/data hashing need their own representative follow-up before generalizing this breakdown.

- [Recorder](case.py), [matrix](matrix.py), [analysis](analyze.py).
- [Manifest](manifest.json), [full phase medians](summary.json), [validation](validation.json).
- Raw cases: `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-10-preparation-phases`.
- The resulting implementation and paired acceptance are in the [lock-handle report](../2026-10-10-controller-lock-handles/report.md).
