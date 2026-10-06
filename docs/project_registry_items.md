# Project registries and logical item receipts

Initialize the intended project **before** launching campaigns:

```bash
flexlock init /path/to/project
flexlock doctor /path/to/project/results/deep --format json
```

`init` creates `.flexlock/project.json`, the existing fingerprint index schema,
and the preset-link directory. Repeating it preserves project identity. It does
not migrate nested indexes or historical outputs. A conflicting `FLEXLOCK_INDEX`
is reported before initialization. `doctor` reports the effective index, environment
override, preset search roots and missing setup without creating files or changing
databases. Existing `.flexlock/` directory and environment discovery remain supported.
To backfill historical evidence, run `flexlock reindex <results_root>` explicitly
after choosing the root; initialization alone does not rebuild old indexes.

## Serial and parallel sweeps

All sweeps use the same `ParallelExecutor` queue/worker/DB path, including
`n_jobs=1` and a single remaining uncached item. One worker executes in the current
process; multiple workers use spawn. `task_record=dir/db` applies consistently.
Independent items continue after one fails, and typed results report each outcome.
CLI execution checks those outcomes and exits nonzero for failure. Standalone
serial `Project.submit(cfg)` still raises the original user exception.

Each result has `task_id`, `task_db`, `record_dir`, `save_dir`, status and payload.
The task ID identifies the queued configuration; it is not a source/input-safe
attempt identity. Existing skip/dedup behavior has not become strict resume.

For distinct output directories, the existing layout stays the same. When several
items share a product `save_dir`, each gets a receipt under:

```text
<campaign_root>/.flexlock-items/<task_id>/<stage_path_digest>/
```

The callable still receives the requested product directory. Completion/result/error
files and output checksum baselines live in the separate receipt directory. The
database retains every item and stage's resolved configuration and source/env/note;
later appends do not replace an earlier item's provenance. In `dir` mode, each
receipt has a full run.lock. In `db` mode, its marker points to the corresponding
task snapshot. Historical delta records inherit fields from their recorded master
through the compatibility reader; missing historical identity is not reconstructed.
`.flexlock-items` does not claim a nested project registry.

Shared-root stages must write disjoint products. Overlapping declared output paths
are rejected before queueing. Undeclared outputs retain historical unchecked
behavior: the library cannot infer that arbitrary user writes are disjoint. A
shared product directory has no new aggregate `run.complete`; a reducer/barrier
must inspect the expected item set and validate scientific coverage.

```python
results = project.submit(
    cfg, sweep=[{"chunk": 0}, {"chunk": 1}],
    n_jobs=1, task_record="db", sweep_root="outputs/campaign",
)
for result in results:
    result.raise_on_failure()
    print(result.task_id, result.save_dir, result.record_dir)
```

`_outputs_` paths describe products relative to `save_dir`. For shared-root items,
completion baselines are read from `record_dir`, so reuse must check the specific
item, not a common directory marker. Indexed lookup and reindex discover item
receipts; `Project.get_result` returns their own payload and actual product path.
Preset links for shared-root items also identify receipt directories. Downstream
consumers obtain products through `${run_lock:<receipt>,config.save_dir}` or the
typed result's `save_dir`, rather than assuming products sit under that receipt.

## Inspect every item

```bash
flexlock items outputs/campaign/run.lock.tasks.db --check-outputs
flexlock items outputs/campaign/run.lock.tasks.db --tag extract --format text
```

The default JSON includes identity, tag, node/job IDs when recorded, timestamps,
resolved config, source snapshot, result/error, recording mode and artifact health.
`list_task_records(db)` and `load_task_record(db, task_id)` expose the same read-only
view. Missing databases are not created, and older schemas are not migrated by
inspection. Product corruption is reported separately from recorded execution status;
inspection never rewrites `done` into another state. `--check-outputs` runs opted-in
project validators and checksum checks; it does not certify undeclared files or
scientific acceptance. Composite snapshots expose their per-stage receipt paths.

## Environment and boundaries

Export the intended source through `PYTHONPATH` for child workers/bootstrap scripts
when using an editable environment that points to another checkout. A parent import
probe or package version alone does not establish which code children execute.

No scheduler-state polling, arbitrary filesystem reservation, attempt/retry history,
identity-safe resume or new plan/launch facade is introduced here. These remain
separate follow-ups. The task DB and item receipts describe execution; project
validators and reports decide whether scientific gates pass.
