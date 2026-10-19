# FlexLock 0.10: smaller execution core

This pre-1.0 release removes automatic execution-time reuse policy. FlexLock
keeps Python configuration, provenance, protected destinations, workers, sweeps,
ordered execution and scheduler submission. Project workflows select artifacts,
check cohort coverage and decide which computation remains scientifically acceptable.

## Breaking API changes

| Removed surface | Supported replacement |
| --- | --- |
| `smart_run` (including `False`), `search_dirs`, submission `match_include` / `match_exclude` | Remove these kwargs. Select upstream producers explicitly; use fresh destinations for new computation. Source capture include/exclude and record comparison remain. |
| CLI `--check-exists` | Concrete producer anchors / `run_lock`; selected-path `--save-dir-policy skip` where intentional. |
| `Project.exists`, `Project.get_result(config)` | Exact-path `load_record`, `RunRecord.load_results`, or explicit selected-path reuse; no equivalent-run search. |
| `submit_chained`, `ChainedResult` | A project loop or the resource-chain coordinator recipe with accepted scheduler IDs. |
| `_skip_complete_=True` composite payloads | Select remaining stages, bind concrete retained producers and choose fresh destinations. Old flagged payloads fail clearly before executing stage bodies. |
| Worker-time unpinned `${run:...}` under `--after` | An explicit pin resolved at submit, or concrete future `${run_lock:/path/to/producer,...}`. No newer producer is selected when the worker starts. |

Obsolete kwargs raise `TypeError` rather than silently launching fresh work.
Do not mechanically replace old `smart_run=True` calls with expensive scientific
reruns. Decide producer selection and destination organization first. Removing
`smart_run=False` is a mechanical caller cleanup when the surrounding workflow
already selects producers explicitly.

## Retained contracts

- `py2cfg`, presets, node replacement with `@`, overrides and named sweep files.
- `run_lock` bindings record selected producer identity and verify it at consumption.
- Source/data provenance, per-invocation `source_scope`, include/exclude declarations,
  nested-target repository discovery, results in authoritative records and record diff.
- Local execution, parallel task claims, Slurm/PBS, `--after`, scheduler profiles,
  preview and existing export/enqueue paths. Scheduler switches can live in profiles.
- Ordered CLI `-s a b` and `submit_pipeline`: distinct records, fail-fast stage order,
  independent items in parallel. Different resources use separate jobs/coordinators.
- Occupied-destination checks before scheduler submission, and active ownership guards
  even with `force`. Force intentionally reruns in place and records the new attempt.
- Exact-path `save_dir_policy='skip'`: requires a complete authoritative producer record
  and validates its recorded outputs, even if the proposed config removes `_outputs_`.
  Returns the producer's config, with retained status name `CACHED`. This does not prove
  equivalence to the proposed config or current code. Incomplete occupied items fail.
- Unchanged recorded queue continuation: done rows stay done and pending rows drain.
  Failed/interrupted rows remain visible; changed payloads do not become equivalent.

A wholly complete selected ordered item may be reused with `skip`. A partially
complete item cannot be resumed from stage markers. For recovery, select the remaining
stages explicitly and bind retained producers. Do not blindly reclaim a partially
executed composite as a whole. Reclaiming stranded plain items requires confirming
that their previous worker is gone.

Submission neither searches nor publishes an equivalent-run index. Explicit index
maintenance and registry/preset inspection utilities remain. `FLEXLOCK_WARN_SMART_RUN`
and cache fallback settings no longer enable submission cache behavior. Data hash
caching remains a separate provenance performance mechanism.

## Workflow and rollout

Use the [central workflow guidelines](workflow_guidelines.md),
[source attribution guidance](source_attribution.md) and executable examples under
`examples/slimmer_workflows/`. Track/arm/run is an optional project organization for
both processing and experiments; explicit processing/product/inference roles and
selected producer anchors keep configuration readable. FlexLock supplies provenance
and execution primitives; deployment and scientific acceptance remain project work.

The release candidate passed 1,086 tests (two skipped, one expected failure).
Additional bounded consumer checks covered Python 3.11 through 3.14. These checks
do not establish scientific equivalence or authorize project reruns.

Upgrade source, dependency pins and environment together after checking shared
workers and active jobs. Keep old queues on matching workers. Never activate removal
of `smart_run=False` while its caller still runs against 0.9.x cache defaults.

Project owners select retained producers and decide when to establish fresh pipeline
baselines. Historical scientific adapters belong in consuming projects.
