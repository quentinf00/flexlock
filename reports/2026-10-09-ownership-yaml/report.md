# Faster safe parsing for active ownership rows

Runtime `1512422`, compared with retained `10e8982` guard behavior. Isolated checkout only; production installation unchanged. No scheduler submissions.

Ownership checks now use PyYAML's optional `CSafeLoader`, with `SafeLoader` fallback. This is the same safe YAML data model previously read with `safe_load`; no OmegaConf construction, schema migration, ownership cache or writer change is introduced. Queue status and destination paths are reread/recomputed on every call. Record readers' separate timestamp-as-string loader is deliberately not reused: ownership retains its existing timestamp semantics.

## Diagnosis and validation

The before profile finds 49,600 YAML decodes when binding 100 evenly spaced producers from 1,000 pending rows. Profiling attributes 20.719 seconds to safe YAML loading, 3.871 to destination extraction (including path resolution), and only 0.056 to SQLite active-row reads. These are instrumented diagnostics, not benchmark wall-clock timings.

Focused acceptance: **126 passed, two expected skips**. Both safe loaders are exercised on historical plain, multi-stage, aliased, unresolved and unlocatable rows. Invalid YAML and unsafe tags prevent entry into the guard. Status transitions, edits to task destinations and symlink retargeting are visible between calls. Existing controller collision, ancestor ownership, pre-submit binding, I/O join and compiled-config tests also pass.

Analysis verifies six equivalent prepared queues / 6,000 task configs, 6,000 completed bindings and 600 future bindings. Both variants reject the active-ancestor stale-artifact counterexample and preserve exact allowed future paths. Prepared file count remains **2,007**.

## Alternating measurements

Three repetitions per variant/fixture, each in a fresh process, sequential on compute-118-39; runtime frozen at `1512422`. Serial config compilation and mocked submission. Synthetic 1,000 × 4 KiB inputs. Binding excludes setup and initial config creation, includes binding copy/transform, ownership and record reads. Raw cases and all repetitions are retained.

| Fixture | Old median | New median |
| --- | ---: | ---: |
| Full 1,000-item preparation | 12.708 s | 11.776 s |
| 1,000 completed-producer bindings | 11.189 s | 9.673 s |
| 100 future bindings / 1,000 pending rows | 13.040 s | 6.490 s |

The pending fixture improves **50.2%**; all three new runs (5.811–6.681 s) are faster than all old runs (12.702–14.536 s). Preparation and terminal fixtures contain no active rows to decode and their ranges overlap; their apparent median gains cannot be attributed confidently to this parsing change. The result applies where the optional C loader is available. Fallback correctness is tested; a fallback speedup is not claimed. A 1,000-future-binding workload was not measured.

The after diagnostic still performs 49,600 decodes: YAML load is now 2.323 profiled seconds, destination extraction 3.474 (including 2.872 across all path resolves), and SQLite 0.052. The next bottleneck is repeated destination extraction/path resolution across active row scans. Profiles include fixture setup outside the binding timer; the after diagnostic overlapped evidence analysis, so these diagnostics establish call distribution, not controlled wall-clock speedup.

Next investigate reducing repeated row scans while retaining fresh status reads, symlink resolution and legacy destination fallbacks. Do not cache an ownership answer across mutable queue changes. File reduction remains planned separately: retain mutex inodes; queue-pointer omission or a pointer/marker merger needs older-reader compatibility. Earlier pointer omission halved files but saved only 6.1% of preparation time and was unsafe before the ancestor guard fix. This fix alone does not upgrade older installed readers.

## Evidence

- [Tests](tests.xml), [validation](validation.json), [manifest](manifest.json), [repetitions](summary.json).
- [Before profile](profile-before.txt), [after profile](profile-after.txt); raw profiles `/tmp/flexlock-active-before.prof` and `/tmp/flexlock-active-after.prof`.
- Drivers: [matrix](matrix.py), [cohort](cohort.py), [preparation](prep.py), [context](context.py), [baseline guard](baseline_guard.py), [analysis](analyze.py).
- Raw cases: `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-09-ownership-yaml`.
