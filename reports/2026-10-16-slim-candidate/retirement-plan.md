# Caching/pipeline simplification: candidate boundary

2026-10-16. Requested: complete simplification, then validate a candidate.
**User decision confirmed:** remove retired APIs now. This pre-1.0 candidate removes
automatic cache selection, marker-based partial-stage resume and chained fanout.
Installed project environments are unchanged; validation uses an isolated candidate.

## Recommended removal boundary

| Surface | Candidate behavior |
| --- | --- |
| submit, run_stage | Fresh execution by default; run_stage can remain a thin wrapper without sibling search |
| smart_run / --check-exists / search_dirs / cache match filters on submission | Retire automatic execution-time cross-run cache selection; explicit True callers must select and bind a producer themselves |
| Project.exists / get_result(config) | Retire equivalent-run search; use exact-path record/results readers and project acceptance |
| Composite _skip_complete_ / marker-driven stage resume | Remove automatic partial-stage skip; reject old flagged payloads rather than silently rerun their completed stages |
| submit_chained / ChainedResult | Replace with project loops and existing resource/accepted-ID ledger recipe |
| Ordered -s a b / submit_pipeline | Keep distinct stage records, fail-fast sequential execution on one allocation, and sweep fanout across independent items |
| Same-path save_dir_policy=skip | Keep explicit selected-path reuse and output/record validation. It must not imply code/config equivalence or resume a partially complete composite |
| Task DB continuation | Keep draining pending rows from an unchanged recorded queue; done rows remain done, failures remain visible |
| Diff/fingerprints/source_scope/data/output checks | Keep provenance/comparison independent of reuse decisions |
| Presets / @ / overrides / sweep files / concrete run_lock / --after | Keep existing supported workflows |
| Maintenance/registry indexes | Keep explicit inspection/reindex utilities where useful; automatic cache-index publication is unnecessary for fresh execution |

The Python signatures now reject obsolete keywords. False-only keyword arguments also need mechanical
cleanup in examples and callers; new records do not require a legacy scientific adapter.
No global search should happen on an ordinary fresh submission. Neither an obsolete
cache flag nor an old queued resume flag may silently turn into destructive fresh work.

## Caller impact

The [bounded audit](caller-inventory.json) covers 32 physical roots and finds 48
literal references in 17 roots. Comments, tutorial/lab exercises and real pipeline
calls are distinguished by source context. Actual uses include older SST preparation,
JEPA pipeline wrappers, template/sample workflows and HAFS scripts. Recent retained
adoption recipes already select artifacts explicitly. Biomass uses explicit skip.

Do not blindly turn scientific smart_run=True calls into fresh expensive computation.
Project owners must wire selected upstreams or intentionally plan fresh end-to-end
runs after API stabilization. The candidate can be validated in isolation before any
project environment is upgraded. Active job environments remain deferred.

## Validation after implementation

1. Fresh Python/CLI submissions make no cache-discovery call; existing destinations
   fail before scheduler submission. Force still cannot bypass active ownership.
2. Exact-path reuse validates authoritative records and declared products; missing,
   corrupted or incomplete products cannot be reported as accepted success.
3. Partial composite recovery is explicit: choose remaining stages, bind exact
   retained predecessors and use fresh destinations. Old resume requests fail clearly.
4. Continue an unchanged queue through task claims; verify frozen membership,
   preserved done rows and honest failed/interrupted status. No stage-equivalence claim.
5. Preserve the five recipes, config/root overrides, upstream sweeps, local workers,
   mocked Slurm chains and failure/coverage rejection. Replace retired behavior tests
   selectively; retain mixed-module loader, guard, source/data and result-reader checks.
6. Run the full suite and isolated installed-wheel checks; repeat 1,000-item preparation
   cases with source/data enabled and disabled, plus a bounded real local item run.
7. Build a local release candidate with migration notes, exact wheel/source identity
   and documented project follow-ups. This does not deploy or launch scientific reruns.

## Pre-change baseline

The existing 10-item tracked smoke passes. A 1,000-item source/data-enabled preparation
on the home filesystem took **8.586 s**, produced 1,000 pending rows and made exactly
one mocked scheduler call. Counted 1,010 non-input files. Input fixture: 1,000 files
of 4 KiB. This is one sample, not a stable throughput or speedup conclusion.
See [measurements](baseline-measurements.json) and [driver](benchmark.py).
No Hydra dependency or environment installation was needed for this FlexLock-only
measurement. All scheduler process boundaries are intercepted or rejected.
