# FlexLock provenance kernel: implementation plan (draft, 2026-11-23)

Option B of [direction.md](direction.md), with Python configs kept. This plan replaces the
release table of [slim-core.md](slim-core.md) §6; that file's census, layout (§4) and sst
analysis (§5) still apply.

## Shape

The `flexlock.kernel` subpackage writes and reads run records. It has two clients:

- **`flexlock-run`** (Python configs, `py2cfg`): unchanged syntax, e.g.
  `flexlock-run -d experiments.baseline.cfg -s train -o width=256`. It fills the record's
  optional `call` block (target, arguments, nested targets).
- **`flexlock record`** (any command): wraps plain scripts, raw arrays and other launchers. It
  writes the same record without the `call` block.

Compare Hydra multirun and direct Submitit as adapters. Both use the same on-disk contract.
Project-owned chains consume submission receipts through the small campaign launcher.
XPCC and ACDM read the same format for both clients. [Campaign launcher](campaign-launcher.md)

Much of the kernel already exists and gets moved out from under the execution engine
(`api.py`, `runner.py`, `worker.py`, `taskdb.py`): `git_utils`, `snapshot`, `data_hash`,
`destination_guard`, `outputs`, `record`/`run_record`, `fingerprint`.

## The record

Use the `.flexrun/` layout as a draft until the prototype below passes. Record each fact when
its owner first knows it.

| When | Owner | Evidence |
|---|---|---|
| Prepare | Caller | Immutable `record.yaml` with destination, declared source scope and tree, environment lock, input identities or upstream references, and output contracts. For a Python stage, include the config origin and optional plain-YAML `call` with the importable target, nested targets, bound arguments and any pending upstream references. XPCC can display it without importing project code or FlexLock. |
| Submit | Launcher | Persist intent before submission. On scheduler acceptance, persist a receipt with attempt, destination, job and array IDs and available log paths. Return it immediately so a dependent job can be submitted while its parents are queued. The campaign ledger can reference this receipt. |
| Start | Worker | Write attempt status, observed source identity and working directory. For a wrapped command, record the concrete argv received by `exec`. Bind pending inputs to their producers and persist the concrete values before invoking the target. |
| Finish | Worker | Validate declared outputs and write `outputs.json` before publishing `run.complete`. On a reported failure, preserve the error and available exit code with `run.failed`. If the worker disappears, use the scheduler receipt to reconcile its state. |

For a shared dataset, prepare one parent record with the expected shard keys and shared source.
Each execution of a shard gets its own attempt under `shards/<id>/`, including its invocation,
status and output manifest. A retry of year 2005 keeps the same shard key and gets a fresh
attempt. Publish dataset completion once every expected shard has a validated success.

## Python API

```python
run = flexlock.prepare(out, sources=[...], inputs=[...], call=None, config=None)  # submission
run.start()     # in the job: check the source tree hash (or use the copied tree), write status
run.finish()    # outputs manifest, run.complete / run.failed
with flexlock.record(out, ...) as run: ...       # one-phase form, for local runs
```

- `prepare` reserves the destination. Preserve exclusive ownership through scheduler acceptance
  and execution, including across concurrent resume requests. An intent with an unknown outcome
  must be reconciled before another writer can claim the same output.
- Managed runs verify the declared source scope and stop before invoking the target on drift.
  With `copy_source=True`, workers execute from a copy captured at submission and shared across
  the array. Include declared helpers and non-Python files. An explicit observation mode may
  continue on drift and must record both the submitted and observed source identities.
- Hashing inputs: `shallow` (size + mtime, for terabyte zarr stores) or `full`. An input that is a
  FlexLock run dir is recorded as an upstream run, not hashed.

## Clients

**`flexlock-run`** imports the config attribute, applies merges and overrides, then calls
`prepare(call=describe(cfg))`. It runs locally or hands a record path to a launcher.
The worker reads the prepared arguments and imports the target from the verified or copied
source. Keep `--print-config`. Replay uses the recorded call and its concrete upstream bindings,
and checks destination changes for every declared output, including absolute paths.

**`flexlock record`:**

```
flexlock record prepare --out DIR [--source PATH]... [--in PATH]... [--config FILE] [--hash shallow|full]
flexlock record exec DIR [--shard ID] -- <command>
flexlock record --out DIR ... -- <command>        # one-phase, local
```

- **Sidecar file:** an optional `flexrun.toml` next to a script declares its sources, inputs and
  outputs once, so the wrapper stays one line.
- Defer Python file-open tracing and XPCC warnings about undeclared inputs until after the
  initial release. An explicitly input-free stage is valid.

## Prototype before freezing schema v1

Use isolated test directories and an existing module-defined `py2cfg` experiment.

1. Run two named arms locally to establish expected outputs. Queue them through each candidate
   adapter. While they are pending, check whether the caller can read both job IDs and
   destinations. Measure the project code required for receipts and bounded concurrency.
2. Edit the config, an imported helper and a declared YAML input to the implementation while
   the jobs are queued. Under verification, a change inside the declared source scope must stop
   the target. Under copied-source execution, check the output value against the submitted
   code, YAML and arguments. Record scientific input files separately from copied source.
3. Rename the original config attribute. Replay the successful call into a fresh directory,
   including a nested target, an upstream reference and an absolute checkpoint path. Verify
   the original input binding, the new checkpoint and the integrity of the original outputs.
4. Prepare a small TC-PRIMED-style dataset and run its commands with stable year keys. Omit a
   required output in one shard. Resume while another is active, then retry the failed shard.
   Verify exclusive ownership, distinct attempt histories, and completion of the dataset only
   after all expected outputs validate. Exercise recovery from an intent with no receipt.

Read the Python and shell attempts through one reader. Freeze schema v1 when it can reconstruct
the submitted and executed invocations to the extent each was known, their source, scheduler
acceptance and outcomes. Choose the adapter using the prototype results.

For changes to run records, completion markers, or scheduler logs, run the ACDM
and XPCC suites in `acceptance-runs/downstream/acdm` and
`acceptance-runs/downstream/xpcc`. Set `PYTHONPATH` to the FlexLock development
checkout and use its Python environment so the cross-project tests exercise the
in-development writer and scheduler adapter.

## Steps

| Step | Content | Acceptance |
|---|---|---|
| 0. 0.10.2 | unique Slurm logs (`%x-%j`), 0644 files, hash cache off SQLite WAL on NFS (quarantine + rebuild), `run.complete` on sweep roots, `--version` | jobs 3957179/3957187-style failures cannot recur; XPCC reads the failing job's own log |
| Prototype | Exercise both clients, receipts, source policies, replay and shard retry in test directories | Pass the prototype above before freezing schema v1 |
| 1. Record + reader (`flexlock/kernel/`) | Freeze the tested schema. Update `load_record`, `status()`, XPCC (`tick.py`, `triage.md`) and ACDM (`walk.py`, `sensors/runs.py`). | Golden records cover old and new layouts, including historical sst task-DB records. Readers for maxss-nf, hafs-jepa, sst and tcwind ship before production writers. |
| 2. Python API | `prepare` / `start` / `finish` / `record()`, reusing the existing modules | unit tests; a local run writes a valid v1 record |
| 3. `flexlock-run` on the API | Prepare the call once and run it locally or through the selected adapter. | Repeat queued-source and fresh-destination replay checks through the public CLI. |
| 4. `flexlock record` CLI | Prepare, exec, one-phase form, shard keys and sidecar declarations. | The XPCC tick reads each attempt of a TC-PRIMED-style array and recognizes dataset completion. |
| 5. Sweeps on arrays | Prepare each item, throttle active tasks and persist receipts. Reconcile outstanding submissions before retry. | Restart a killed sweep. Active shards retain their reservations, completed shards retain validated outputs, and failed shards get new attempts. |
| 6. Chains | campaign launcher on the API; B-CONV run (four GPU fits → one CPU scorer) | ledger + job ids readable by XPCC; then decide on Snakemake or Dagster |
| 7. Migration + removal | hafs-jepa (with the `run.complete` rename in 21 scripts), then maxss-nf, then sst; then remove `taskdb`, `worker`, `backends`, `query`, `mlflow`, PBS | each project's runs and attempts still resolve in XPCC |

## Releases

| Release | Steps | Consumers |
|---|---|---|
| 0.10.2 | 0 | pin bump only |
| 0.11 | Prototype, then 1–3 | Ship XPCC and ACDM readers before enabling new writers. Update the template and pin after validating the existing CLI workflow. |
| 0.11.x | 4–5 | data-prep scripts adopt `flexlock record`; sweep users |
| 0.12 | 6–7 | template "Campaigns"; xpcc-orders; sst launcher retired; old engine removed |

The old engine keeps working until 0.12.

## Orchestrators later (Prefect, Dagster)

The files stay the source of truth, and any orchestrator UI is a view on them. The record stores
the orchestrator's run id, and the orchestrator stores a link to the record. The kernel depends on
neither tool.

- **Dagster** fits provenance better. Its assets, partitions and lineage map onto records and arrays;
  an IO manager could write to guarded destinations; Pipes lets a Slurm job running
  `flexlock record exec` report back.
- **Prefect** fits orchestration (retries, state hooks) but records no data.
- **Cost of either:** a long-lived service on the cluster, with Postgres rather than SQLite on NFS.

Revisit only if chains outgrow the campaign launcher or more people use the system.

## Risks

- **Step 1 is the riskiest.** A reader that misses a layout breaks the tick, triage and ACDM
  silently. Hence golden files from every project, and readers first.
- **Incomplete input declarations limit replay.** Use the sidecar for repeated commands and
  record the identity method for each declared input so readers can judge its strength.
- **A live checkout can drift while a job waits.** Verify the declared scope at start and use
  copied source for jobs that must survive further edits.
- **Old queues still own destinations.** Test exclusion between old and new writers during the
  transition. Preserve historical task-DB reads after retiring the old execution engine.

Migrate sst last. Its working-tree cleanup can proceed independently of 0.11. Include its
historical records in the first reader fixtures so compatibility is tested before migration.
