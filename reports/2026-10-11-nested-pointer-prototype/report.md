# Nested queue pointers: measured saving and reader boundary

Report-only prototype; runtime writers and production installations are unchanged.
The current reader already probes fixed ancestor queue filenames. A new product
nested beneath its queue can therefore be located without a per-product pointer.
The prototype omits pointers only for those new nested products. External products
and existing pointers retain the current writer. Durable mutex files remain.

Three alternating pairs of 1,000-item source/data-enabled preparation, fresh
processes sequentially on compute-116-7 with 16 affinity CPUs, serial compilation, mocked scheduler.
Runtime frozen at `f5f5156`; independent hash caches selected before imports.

| Median / count | Current writer | Prototype |
| --- | ---: | ---: |
| Full preparation | 17.529 s | 13.335 s |
| Prepared case files | 2,007 | 1,007 |
| Queue pointers | 1,000 | zero |
| Durable mutexes | 1,001 | 1,001 |

The median reduction is 23.9%; every prototype repetition improves its pair.
Individual pairs are 17.717/13.335, 17.529/13.978 and 17.080/13.198 seconds.
This new result is specific to tracked preparation after the reader and metadata
optimizations; it does not retroactively replace the earlier 6.1% pointer prototype
or establish a universal filesystem saving. Sibling hash-cache files are excluded
from the prepared case count. This preserves mutexes rather than halving ownership
protection; external destinations do not receive this file reduction.

[Validation](summary.json): six equivalent queues / 6,000 configs, matching master
source trees and input hashes. Current active-destination reads detect the first,
middle and last pending product with and without pointers, without changing DB
bytes. The separate [compatibility probe](compatibility.json) verifies pending and
running replacement work: current required bindings and controller guards reject;
an explicitly allowed future binding preserves the selected path and captures no
old artifact. External pointers remain necessary and effective.

The retained `1244e70` reader misses a pointerless nested replacement and binds
the old artifact. Adding the current pointer makes that older reader detect the
same pending/running work. This is a real provenance boundary, not merely an
optional pointer for older installations. Optional/default resolver semantics are
unchanged by this experiment and are not strengthened by its required-binding checks.

## Proposed migration, requiring user validation

Recommend proceeding only with an explicit requirement for updated readers of
newly prepared runs. Keep legacy pointer/marker/full-lock readers, external
pointers, existing pointers and mutex inodes. Do not delete locators from existing
cohorts or change completed historical evidence.

1. Define and document a versioned queue-layout declaration in the master receipt
   for new ancestor-located products. Establish a supported reader release that
   includes the ancestor ownership fix (`8ad211c` or later), rather than relying
   on the unchanged `0.9.0` string across divergent checkouts.
2. Inventory and pin the actual reader/worker revisions in each adopting project
   and environment. Verify required binding, pending/running refusal, future
   inputs, shared roots, external paths and archive/export behavior before enabling
   the writer. No project installation is changed by this report.
3. Enable omission only for fresh nested products with an authoritative ancestor
   queue; preserve current writing for external destinations and existing pointers.
   Retain historical reading. Measure actual consumer layouts, where external
   products and existing pointers may make the saving smaller.

A version field alone cannot protect an older reader that never looks at the
ancestor master. Requiring updated readers is an operational compatibility
decision. If old installations must keep consuming newly prepared queues, retain
the existing per-product pointers. Both branches preserve current historical records.
No new public flag or default writer change has been implemented.

Evidence: [matrix](matrix.py), [prototype](case.py), [reader probe](probe.py),
[analysis](analyze.py). Raw runs:
`/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-11-pointer-experiment`.
