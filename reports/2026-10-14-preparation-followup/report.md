# Preparation follow-up and consumer integrity cost

2026-10-14; read-only runtime audit plus a bounded synthetic probe. No runtime,
installed environment, project, scientific output or scheduler changes.

## Preparation priorities

Retained phase accounting measures plain/producer compilation at 2.585/6.723 s,
preflight at 2.409/2.492 s and reservation writes at 1.179/1.217 s per 1,000
items. SQLite writes are only 0.023/0.024 s in that uncontended fixture. These
overlap; they cannot be added. The subsequent bounded handle preparation and
source regrouping changes already addressed specific redundancies. Remaining
fresh source capture cannot be amortized blindly across code changes.

The layout-2 prototype measured 2,007 → 1,007 files and 17.529 → 13.335 s median.
Those remain prototype timings, not fresh measurements of the installed 0.9.2
release. Avoid introducing process compilation or async integrity checks on this
evidence: process compilation retained severe outliers, and successful completion
must still wait for required evidence.

Task hashing occurs in executor initial membership, default tag creation, queue
insertion, run-time reuse selection and Project result construction. Prior phase
accounting measured five hashes/item at 0.459/0.931 s. The current bounded
[probe](probe.py) measures 5,000 hashes of 1,000 small synthetic DictConfigs in
0.195/0.419/0.480 s; median 0.419 s. This is a CPU diagnosis, not a new full
submission benchmark. Reuse at the immediate constructor/default-tag boundary
could avoid one pass without caching later mutable inputs. No implementation is
proposed yet: expected gain is modest and must preserve monkeypatch/public helper
behavior, mutation semantics and duplicate-task tag identity. Global identity or
mtime caches are inappropriate.

## Multi-GB producer products

The incoming MaxSS pilot reports repeated output SHA256 checks at consumer starts.
The project helper `maxss_diff.flexlock_bindings.require_product` explicitly calls
`validate_outputs` on the producer's whole config. Core `run_lock` resolution and
`load_record` read/digest provenance without implicitly hashing producer products.
Core hashes opt-in output contracts at completion and at explicit output-health or
reuse validation sites. Thus this concern is partly a project acceptance-helper
cost, rather than a mandatory resolver cost. No real large-file throughput was
measured in this investigation.

A verified record digest cannot replace verification of current product bytes.
The focused control creates an output baseline, changes bytes with the same size
and restored mtime, leaves the record digest unchanged, and confirms validation
rejects corruption. [Results](probe.json) retain all timings and assertions.

Safe immediate recommendation: inspect each consumer wrapper for duplicate
validation of the same producer during one start; remove only duplicate calls
with no intervening computation or mutation, keeping one fresh integrity check.
Also establish whether validating every declared producer output is necessary
when only one product is consumed. Selecting a narrower declared contract can
be project-owned, provided that acceptance documents that scope explicitly.
Changing core validation scope or trusting immutable-storage guarantees would
be an explicit integrity-policy/API decision. Do not implement a persistent
verified-digest cache, mtime shortcut, or after-success background verification.

## Next bounded work

1. Project agents report wrapper-level validation count, consumed products,
   sizes and timing; central review checks scope and eliminates duplicates.
2. Profile a current layout-2 producer-bearing preparation only when evaluating
   a concrete internal change. Keep cache discovery excluded, serial compilation,
   fresh ownership validation and source/data evidence.
3. Consider constructor-local task-ID reuse after confirming it is material;
   prioritize producer binding/config construction if current measurements still
   match the retained phase diagnosis.

The probe first ran against the isolated environment's installed package; that
unretained diagnostic was discarded. Retained results explicitly select this
checkout through `PYTHONPATH`. No performance improvement is claimed.
