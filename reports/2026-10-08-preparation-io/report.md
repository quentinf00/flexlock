# Bounded preparation I/O — 2026-10-08

**Two bounded I/O workers are now the default.** The interleaved 1,000-item
comparison measured a **15.249s median versus 16.120s with the original guard**
(5.4%, three repeats each). Reservation writes fell from a 2.661s median to 1.509s.
Four workers had essentially the same overall median with more variation, so two
was selected. Preparation remains too slow; file count remains 2,007.

Runtime commits: **7dd2217** (deduplication and bounded I/O paths) and **a27a304**
(two-worker default), on the isolated validation branch. Production installations
are unchanged. This is joined, synchronous preparation: required checks and writes
finish before scheduler submission.

## Scope and ownership

Destination preflight probes each unique ancestor database path once per guarded
invocation. It retains own-directory queues, legacy ancestor queues and markers,
current queue pointers and active-row checks. Product paths remain individually
locked with the same lock inodes. Locks are acquired in sorted order by the
controller before parallel metadata reads start.

A private thread pool runs product pointer/marker reads, deduplicated ancestor
existence checks and reservation file writes. Reservation aliases are normalized
and deduplicated before concurrent writes, so two spellings of one product cannot
race on its temporary pointer. The authoritative queue path is computed once.
Every pool is joined before proceeding, including on exceptions. Failed preflight
or reservation prevents dispatch; failures do not promise rollback of already
persisted queue rows or partial reservation files.

Config resolution still uses the controller because resolver registration is
global. SQLite commits, active-row interpretation, collision decisions, lock
acquisition/release and scheduler submission remain coordinated. Pools have
finished before local/scientific worker execution. No public concurrency argument,
new queue format, deferred required check or process-compilation mode was added.

## Correctness

**120 focused tests pass, with two expected serial-only skips**, on the chosen
default (65.89s). The earlier four-worker focused run passed 117 cases. Additional
I/O tests exercise 1/2/4 workers, once-per-ancestor probes, legacy ancestor ownership,
alias deduplication, reservation completion and injected failures. Join-order cases
skip with one worker because they require two simultaneously running operations.
They prove that failures retain controller ownership until outstanding work exits.
Reservation failure explicitly prevents backend submission for all three counts.
Existing checks cover held/pending queues, forced replacement refusal, cross-tag
reuse, completed output validation, producer replacement and pipeline receipts.

The initial additional scheduler-failure fixture used an unsupported `dir_suffix`
keyword and failed before reaching preparation. Its corrected distinct-destination
fixture passed at 1/2/4 workers; the initial error and recheck XML remain retained.
This was a test construction error, not a runtime regression.

All 12 comparison queues contain 1,000 equivalent pending item payloads after
normalizing only output prefixes, with one pickle, one `0-3` worker script and one
mocked scheduler call. Submission cases execute no products. All 100 local smoke
products independently match item IDs and input SHA-256 values. Source-aware
preparation retains explicit filtered source capture. No real Slurm submission,
production adoption or full-suite/scientific scaling claim is made.

## Interleaved measurements

The comparison uses the original guard/reservation implementation from **6211ef6**
on the same otherwise unchanged runtime as the new variants, loaded as an isolated
module and substituted before measurement. The comparator's source and checksum
are retained. All 12 cases ran with checkout revision **7dd2217**, held fixed.
Each case starts in a fresh process/output directory; framework imports precede
the timer. The original/1/2/4 order rotates across repeats. Threads affect controller
metadata I/O only; the mocked Slurm array has four scientific task workers in every
case. Same 1,000 deterministic 4 KiB inputs and cache-off directory-record contract.

| Variant | Repeat 1 | Repeat 2 | Repeat 3 | Median |
|---|---:|---:|---:|---:|
| Original guard/reservations | 16.120s | 18.072s | 16.001s | 16.120s |
| Deduplicated, 1 I/O worker | 18.200s | 17.724s | 15.662s | 17.724s |
| Deduplicated, 2 I/O workers | 15.185s | 15.526s | 15.249s | 15.249s |
| Deduplicated, 4 I/O workers | 15.223s | 14.441s | 17.628s | 15.223s |

Two workers were faster than the original in all three corresponding repeats;
four were slower in one. The 0.027s median difference between two and four is too
small to justify the additional concurrency. Deduplication alone did not establish
an elapsed-time gain. Filesystem/host variation remains substantial: three repeats
on one NFS host do not establish a universal speedup.

| Median phase | Original | 1 worker | 2 workers | 4 workers |
|---|---:|---:|---:|---:|
| Guard entry/preflight | 3.064s | 3.559s | 2.848s | 3.462s |
| Reservation writes | 2.661s | 3.062s | 1.509s | 0.978s |

These are unprofiled wall-clock timers. They overlap with larger executor timers,
so do not sum all recorded phases. Parallel reservation writes have the clearest
benefit; preflight gains are less convincing. The file count is **2,007** for every
variant. No source changes were made during the comparison.

After committing the chosen default at **a27a304**, separate acceptance samples
measured **13.780s** for cache-off preparation and **17.465s** for explicit
source-aware preparation (1,000 items each). Local smoke took **8.805s**, 100 items.
These single samples confirm the installed-checkout behavior; they are not
additional medians or evidence that source capture is a fixed 3.7-second cost.
Do not compare the 15.249s interleaved median directly with earlier grouped runs
as if host conditions were identical.

## Next boundary

The experiment answers the parallelization question for independent metadata I/O.
Configuration work remains substantial. A batched process-compilation prototype
would need explicit handling of custom resolver registration, selection/lineage
semantics, module imports, serialization and startup cost; a thread pool around
current config resolution would race on the global resolver registry. Investigate
safe config reuse alongside that prototype before adding a new execution mode.

Pointer/marker consolidation, tracked-worker source costs, cache-discovery
migration and escaped-literal compatibility remain separate work. Required guards
remain before dispatch, even if future preparation gains more concurrency.

Evidence: [comparison manifest](comparison-manifest.json), [summary](summary.json),
[validation](validation.json), [initial tests](initial-tests.xml),
[default tests](default-tests.xml), [I/O rechecks](io-tests.xml),
[fixture error](fixture-error.xml), [default measurement](default-measurement.json),
[source manifest](source-manifest.json), [source lock](source-controller-lock.yaml),
[local smoke](local-smoke.json), [source hashes](source-evidence.json).
The [matrix driver](io_matrix.py), [phase timer driver](phase_timers.py),
[original guard](baseline_guard.py) and [analysis](analyze.py) are retained.
Drivers use the original `/tmp` helper paths recorded in the manifest; restore
those files from the retained copies when replaying after temporary-file cleanup.
Raw artifacts remain under `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-prep-io-*`.
