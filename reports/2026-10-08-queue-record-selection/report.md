# Queue record selection and parsing — 2026-10-08

Queue preparation now avoids decoding irrelevant rows, reuses result task hashes,
and uses optional safe LibYAML record parsing. **No meaningful additional overall
speedup is established:** the 1,000-item median is 19.948s versus 20.209s previously
(1.3%, three repeats, with substantial variation). The remaining work is still too
slow. The commits are **99fda5c** (selection/hash reuse) and **6211ef6** (optional
safe C loader), on the isolated validation branch; production installs are unchanged.

## Change and preserved contracts

A private record-reader selector filters terminal statuses in SQL and requested
identities before payload decoding. Executor startup validates only requested
completed receipts and checks requested prior failures/interruption; pending rows
need neither decoding nor receipt materialization at that point. Constructor
append checking still includes every completed historical row across tags.

Sweep result collection decodes only requested identities and computes each task
hash once. It deliberately does not filter by the invocation's tag: identical
completed items retained under an older tag still belong to the request. Public
record-reader signatures, record shapes, typed results, queue serialization and
bookkeeping formats are unchanged. This is selection before decoding, not a cache
of mutable queue state; results are still read after execution/submission.

Record YAML parsing selects `CSafeLoader` when available and falls back to
`SafeLoader`. The existing implicit-timestamp exclusion remains: unquoted ISO
timestamps stay strings, as expected by OmegaConf. Safe constructors are retained,
and no additional dependency or configuration flag is introduced.

## Acceptance

**155 focused tests pass in the final run (123.44s).** The preceding selection-only
suite had 117 passes. New tests prove that terminal receipt checks do not decode
pending rows; result collection skips unrelated payloads while retaining cross-tag
history; legacy schemas retain their record shape; and C/Python safe record loaders
agree for timestamps, native scalars, aliases/merge keys, binary/set values and
literal resolver text. Python object tags remain rejected. Existing tests cover
cross-tag completed output validation, prior terminal failures, pipeline receipts,
append collisions, force/active queue guards and producer binding/replacement.

All six before/final queues have equivalent task payloads after normalizing only
each output prefix. Each contains 1,000 pending items, one task pickle, one `0-3`
array script and one mocked scheduler call; there are no executed products in
submission cases. The 100-item local smoke completed and every product ID/checksum
matches its input. A source-tracked preparation sample preserves explicit filtered
source capture. No real scheduler submission, production adoption or full-suite
claim is made.

## Timing and profile evidence

Same fixture set and harness as [the preceding slice](../2026-10-08-freeze-binding-reuse/report.md):
1,000 deterministic 4 KiB inputs, cache off, directory task records, NFS home
storage, four fixed workers. Imports precede the timer; each source revision stayed
frozen during sequential measurements. Runs are grouped, not interleaved; host load
varied. Manifests retain exact commands, revisions, versions and load averages.

| 1,000 items | Repeat 1 | Repeat 2 | Repeat 3 | Median |
|---|---:|---:|---:|---:|
| Previous baseline, a32d227 | 18.322s | 20.209s | 21.232s | 20.209s |
| Selection/hash reuse only, 99fda5c | 20.896s | 20.785s | 19.526s | 20.785s |
| Selection + safe C loader, 6211ef6 | 19.731s | 19.948s | 25.770s | 19.948s |

Selection alone did not improve elapsed time. The final 1.3% median reduction is
insufficient evidence for a meaningful speedup. Peak RSS medians: 142,788 → 141,124
KiB (about 1.6 MiB lower); file count remains **2,007**. Source-tracked preparation:
**15.920s** in one sample. Local smoke: **8.141s**, one sample; neither establishes
an execution speedup. The variation in these samples warrants matched comparisons
for subsequent acceptance.

In the 100-item profile, record selection/materialization took **0.068 cumulative
seconds**, versus **1.004s** for the previous reader; selection alone took 0.521s.
Task hashing fell **600 → 500 calls**. OmegaConf creations remain 204 and merges
201. The final profiled run took 4.195s. Cumulative/profiled times overlap and do
not explain the unprofiled elapsed time by themselves.

## Unprofiled wall-clock phases

Because decoding improvements did not establish an elapsed-time gain, a separate
[diagnostic driver](phase_timers.py) wraps call sites outside production code.
Its single 1,000-item run took **14.617s**. It used the same frozen runtime and
fixture contents, a different fresh output prefix and no cProfile. Do not use that
single faster run as the accepted overall timing result.

| Timer | Calls | Wall-clock seconds |
|---|---:|---:|
| Merges across compilation/executor | 2,001 | 3.476 |
| Freeze/bind across compilation | 1,000 | 2.962 |
| Guard acquisition/preflight | 1 | 2.347 |
| Guard release | 1 | 0.393 |
| Reservation pointer writes | 1 | 2.082 |
| Queue insertion/serialization | 1 | 1.300 |
| Record selection/materialization | 2 | 0.248 |
| Result collection (includes one record read) | 1 | 0.404 |
| Executor constructor (includes merges/queue/reservations) | 1 | 6.246 |
| Executor run | 1 | 0.253 |

Nested timers overlap: do not sum the entire table. Merging/freezing account for
about 6.4s in that run. Guard entry/exit and reservation writes together take
about 4.8s. Record decoding is now a small fraction. This redirects the next
optimization toward configuration work and guard/metadata I/O.

## Next action

First inspect repeated ancestor filesystem probes during destination preflight.
Many products share ancestors, but the current guard repeats existence checks for
each product. Deduplicate those probes within one guarded invocation while
preserving per-product lock inodes, legacy marker/ancestor ownership and active
queue refusal. Measure with phase timers and matched fresh comparisons; do not
remove mechanical guards to reduce file count.

Pointer/marker consolidation and master-default config reuse require separate
compatibility designs. Tracked-worker source checks, automatic cache discovery
migration and the previously demonstrated escaped-literal limitation remain open.

Evidence: [summary](summary.json), [validation](validation.json),
[before manifest](before-manifest.json), [selection-only manifest](selection-only-manifest.json),
[final manifest](after-manifest.json), [source manifest](source-manifest.json),
[profiles](profiles.json), [selection tests](selection-tests.xml), [final tests](tests.xml),
[wall-clock phases](wall-clock-phases.json), [phase measurement](phase-measurement.json),
[loader/runtime details](runtime-loader.json), [source lock](source-controller-lock.yaml),
[source hashes](source-evidence.json). [analyze.py](analyze.py) recomputes queue/product
comparisons; raw artifacts remain under `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-prep-*`.
