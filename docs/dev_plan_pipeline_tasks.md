# Dev plan: composite pipeline tasks — multi-stage × sweep × HPC × enqueue

Branch: `pipeline-tasks` (worktree of `flexlock` @ 0a4726d, v0.8.1).

Integration with `env-fingerprint` uses one stage executor for plain and
composite tasks, retaining batched claims/completions, task tags, full run
records, preset links, and code-drift detection. Composite DB snapshots store
each executed stage under `stages[absolute_save_dir]`; the record reader
selects that stage and exports materialize all stages with the master.

## Goal

Lift the restriction that multi-stage selection (`flexlock-run -s train linear_probe`)
is incompatible with `--sweep*`, `--slurm-config`/`--pbs-config`, and `--enqueue`
(`runner.py::_validate_multiselect`). Additionally make `--sweep` + `--enqueue`
work in the single-stage path (today the enqueue branch returns before
`load_sweep` is called, silently dropping the sweep).

## Core design: composite pipeline tasks

A task in the sweep task DB may be a **stage sequence** instead of a single
config:

```yaml
_stages_:
  - {_target_: ..., save_dir: results/xp1/train, ...}       # fully compiled stage cfg
  - {_target_: ..., save_dir: results/xp1/linear_probe, ...}
```

- One sweep item = one composite task = the whole stage sequence for that item.
- The **worker** runs a composite task's stages sequentially, guaranteeing
  intra-item ordering by construction. Parallelism (local `n_jobs`, Slurm/PBS
  array workers) fans out **across items**.
- Plain dict tasks keep their exact current behaviour. `_hash_task`,
  `queue_tasks`, tags, resume, orphan reconciliation, `flexlock-status` all
  work unchanged — `task_info` is opaque YAML; **no DB schema change**.
- Stage configs are compiled and frozen at build time (root refs baked by
  `select_and_freeze_root_refs`, then `freeze_deferred` per stage so
  `${run_lock:}`/`${latest:}` stay deferred and fire on the worker at stage
  start). A composite task is therefore self-contained: never re-merge the
  base config into it at dequeue time.

Semantics for multi-stage sweeps (docs §14g `pipeline_dir` pattern): each sweep
item merges into the **root** config *before* selection (respecting
`--sweep-target` as a root dot-path), then every stage is re-selected and
re-frozen from that merged root. `-s train linear_probe --sweep
pipeline_dir=xp1,xp2` → 2 composite tasks × 2 stages.

Known accepted limitation (document it): all stages of an item run inside one
scheduler job / worker slot, so per-stage HPC resource configs are not
possible. Scheduler-level `--dependency` chaining is a possible later
enhancement, out of scope here.

## Phase 1 — worker: execute composite tasks

`flexlock/worker.py::worker_loop`

1. Refactor the current per-task body (merge → `resolve_deferred` →
   `extract_tracking_info` → fingerprint → `snapshot(parent_lock=master)` →
   `.flexlock_marker` → `func(cfg)` → `results.json` → `mark_complete` →
   `index.record_task`) into a helper, e.g.
   `_run_stage(func, cfg, task_to, db_path, db_dir, master_lock, stage, node, task_id) -> (save_dir, result)`.
   Keep behaviour byte-identical for plain tasks (they call it once).
2. Detect composite tasks: `isinstance(task, (dict, DictConfig))` and
   `"_stages_" in task`. For those:
   - Iterate `task["_stages_"]` in order; run each stage through `_run_stage`.
   - Stage-level resume: honour an optional `_skip_complete_: true` key on the
     composite task — if a stage's `save_dir` already has `run.complete`, log
     and skip it (mirrors `--check-exists` semantics). Without the key, run
     every stage (collision guard was applied driver-side).
   - On stage failure: write `run.error` in that stage's dir (existing
     `RunRecord.write_error`, include stage index), **abort the remaining
     stages**, and `finish_task(db_path, task, error=...)` with the traceback
     prefixed by which stage failed (e.g. `"[stage 1/2 linear_probe] ..."`).
   - On success of all stages: `finish_task(..., result=<per-stage list>)`
     where the result is `[{"save_dir": ..., "result": ...}, ...]` (must stay
     `yaml.safe_dump`-able — `taskdb._to_yaml` raises on arbitrary objects).
   - `.flexlock_marker` per stage dir points at the shared DB + the composite
     `task_id` (same as today's single-task marker).
3. KeyboardInterrupt mid-item: `finish_task(status="interrupted")` as today;
   completed stage dirs keep their `run.complete` so a reclaim resumes past
   them when `_skip_complete_` is set.

## Phase 2 — api: `Project.submit_pipeline`

`flexlock/api.py`

New method (name it `submit_pipeline`; keep `_submit_sweep` untouched):

```python
def submit_pipeline(self, items: "List[List[DictConfig]]", *, n_jobs=1,
                    smart_run=False, search_dirs=None, slurm_config=None,
                    pbs_config=None, wait=True, sweep_root=None, tag=None,
                    force=False, timeout=None, note=None,
                    save_dir_policy=None, debug=False,
                    dry_run=False) -> "List[List[ExecutionResult]]":
```

1. **Serialization**: composite task dict per item =
   `{"_stages_": [OmegaConf.to_container(stage, resolve=False, throw_on_missing=False), ...]}`.
   Stages arrive already frozen (`freeze_deferred` applied by the caller).
   When `smart_run`/check-exists is requested, set `"_skip_complete_": True`
   on the task dict.
2. **DB root**: `sweep_root` if given, else the item root per item =
   `os.path.commonpath` of that item's stage `save_dir`s (the pipeline dir),
   and the master root = commonpath of the item roots. For a single item the
   master root is its pipeline dir. Task DB lives at
   `<master_root>/run.lock.tasks.db` via the existing
   `ParallelExecutor(cfg=executor_cfg)` convention
   (`executor_cfg = {"save_dir": str(master_root), "_snapshot_": {}}`).
3. **Containment validation**: every stage `save_dir` must nest under the
   master root unless `sweep_root` was explicitly provided (mirror
   `_validate_sweep_save_dirs`, including the helpful error text suggesting
   `--sweep-root`). Raise `FlexLockValidationError` before queueing anything.
4. **Collision guard** (`save_dir_policy`): naming policies
   (increment/timestamp) don't compose cleanly with pre-baked cross-stage
   paths — reject them with a clear `FlexLockValidationError` for pipelines.
   Guard policies apply per stage dir, driver-side, before queueing:
   `raise` (default, unless `force`), `overwrite` (`clean_run_dir`), `skip`
   (→ set `_skip_complete_`), `unsafe` (no check).
5. **force**: unlink each stage's `run.complete`/`results.json` and reset the
   task DB (reuse `_reset_sweep_for_force` shape; DB files at master root).
6. **smart_run (driver-side)**: optional first cut — for each item, if *every*
   stage cache-hits `_find_matching_run`, return CACHED results for the item
   without queueing it. Partial hits: queue the item with `_skip_complete_`.
   (Keep simple; per-stage fingerprint checks on the worker are out of scope.)
7. **Dispatch**: one `ParallelExecutor(func=instantiate, tasks=composite_tasks,
   task_target=None, cfg=executor_cfg, n_jobs=..., slurm_config=...,
   pbs_config=..., tag=..., note=...)`; `executor.run(wait=wait, timeout=...)`.
8. **dry_run** (HPC): render the submission script via the existing
   `_preview_hpc_script` and return without queueing (call it before
   `ParallelExecutor` is constructed so the DB isn't touched).
9. **Results**: after the run, build `List[List[ExecutionResult]]` (items ×
   stages) from the task DB rows: composite row status maps to the item; per
   stage, prefer the stage dir's `results.json` / `run.complete` (a stage that
   ran before a later-stage failure is SUCCESS; unreached stages are
   SUBMITTED/INTERRUPTED; the failing stage FAILED with the row's error).
   Reuse/extend `collect_results` or add `collect_pipeline_results`.
   `wait=False` → all-`SUBMITTED` skeleton results.

## Phase 3 — runner: wire `_run_multi` to sweeps, HPC, enqueue

`flexlock/runner.py`

1. `_validate_multiselect`: **remove** `--sweep/--sweep-file/--sweep-key`,
   `--slurm-config/--pbs-config`, and `--enqueue` from the offending list.
   Keep `-O`/`-M` and `-e/--edit-config` rejected. Update the `--select` help
   string and the error text.
2. `_run_multi` rework:
   - `sweep_tasks = load_sweep(...)` (same call as the single-stage path);
     `items = sweep_tasks or [None]` (`None` = no override).
   - Per item: `merged_root = root_cfg` if item is `None` else
     `merge_task_into_cfg(root_cfg, item, args.sweep_target)` (root-level
     merge, pre-selection). Then per stage:
     `stage_cfg = self._build_node_cfg(args, merged_root, base_cfg, sel)`
     followed by `freeze_deferred(stage_cfg)`.
   - `--print-config` / `--dump`: iterate items × stages with
     `# --- item i / stage sel ---` headers, then return (as today).
   - `--enqueue FILE`: append one
     `{"_stages_": [to_container(stage, resolve=False), ...]}` dict per item
     via `enqueue_to_file`; log count; return.
   - `--check`: run `Project.check` per stage config (item-merged), aggregate
     errors with item/stage labels.
   - Otherwise dispatch:
     `proj.submit_pipeline(items_stages, n_jobs=args.n_jobs,
     smart_run=bool(args.check_exists), slurm_config=..., pbs_config=...,
     sweep_root=args.sweep_root, dry_run=..., note=..., force=...,
     save_dir_policy=..., debug=debug)`.
   - Return shape back-compat: single item → return the flat per-stage list of
     raw results (matches today's `_run_multi` return); multiple items →
     list of lists.
   - Keep the current local sequential path? **No** — route everything through
     `submit_pipeline` (single item, n_jobs=1, local == worker_loop in-process,
     same ordering). BUT: this changes the current multi-select behaviour from
     direct `proj.submit` per stage to the task-DB path. If test fallout is
     large, keep the old direct path for the no-sweep/no-HPC/no-enqueue case
     and use `submit_pipeline` otherwise — decide by test results, prefer one
     path if green.

## Phase 4 — dequeue: composite entries in `--sweep-file`

`flexlock/runner.py::run` (single-stage path), possibly `utils.load_sweep`.

1. After `load_sweep`, partition items: composite (`"_stages_"` key) vs plain.
2. All-composite → route to `proj.submit_pipeline` (items already compiled;
   do NOT merge the base config into them).
3. Mixed queues: **normalize plain items** by merging into the compiled node
   config (`merge_task_into_cfg(node_cfg, item, args.sweep_target)` +
   `freeze_deferred`) and wrapping as single-stage composites — then the whole
   queue goes through `submit_pipeline` uniformly. Only do this when at least
   one composite entry is present; a purely plain queue keeps the existing
   `proj.submit(sweep=...)` path untouched (no regression risk).
4. Containment: composite items validate against their pipeline dirs (Phase 2
   logic); recommend `--sweep-root` in the error message.

## Phase 5 — single-stage `--sweep` + `--enqueue`

`flexlock/runner.py::run`

1. Move the `args.enqueue` branch **below** the `load_sweep` call.
2. `sweep_tasks` empty → current behaviour (enqueue the compiled node config).
3. `sweep_tasks` non-empty → for each item, mirror the `print_config` sweep
   preview in `Project.submit` (api.py ~631): `merge_task_into_cfg(node_cfg,
   item, args.sweep_target)` + `freeze_deferred`, then
   `enqueue_to_file(args.enqueue, to_container(resolve=False))` per item.
   Log the total.

## Tests

Follow existing patterns (`tests/test_multistage_config.py`,
`test_dump_enqueue.py`, `test_parallel.py`, `test_runner.py`). New coverage,
roughly in `tests/test_pipeline_tasks.py` (+ edits to
`test_multistage_config.py` where it asserts the old rejections):

- worker: composite task runs stages in order (record call order via a target
  writing to a shared file); mid-item failure aborts remaining stages, DB row
  `failed` with stage-labelled error, earlier stage dirs have `run.complete`;
  `_skip_complete_` skips completed stage dirs.
- api: `submit_pipeline` local n_jobs=1 and n_jobs=2 (2 items × 2 stages,
  intra-item ordering preserved, items parallel); containment validation error
  + `sweep_root` opt-out; `force` resets markers+DB; naming policies rejected;
  result shape items × stages; `wait=False` returns SUBMITTED.
- runner: `-s a b --sweep k=v1,v2` builds 2×2 configs with item merged at root
  pre-selection (assert a `${pipeline_dir}`-style root ref differs per item);
  `--print-config`/`--dump`/`--check` iterate items × stages; `-O`/`-M`/`-e`
  still rejected; old sweep/HPC/enqueue rejections **removed**.
- enqueue/dequeue roundtrip: `-s a b --enqueue q.yaml` twice with different
  `-o pipeline_dir=...` → 2 composite entries; `--sweep-file q.yaml` runs both
  items correctly (no base re-merge); mixed queue (1 plain + 1 composite) runs
  both; single-stage `--sweep 0.1,0.2 --sweep-target lr --enqueue q.yaml` →
  2 merged plain entries; deferred resolvers survive the roundtrip unresolved.
- HPC: no cluster in CI — test the dispatch boundary: `submit_pipeline` with
  `slurm_config` + `dry_run=True` renders a script without touching the DB;
  monkeypatch `SlurmBackend.submit` to run `worker_loop` inline and assert the
  composite path completes (pattern likely exists in `test_parallel.py`).

Run the full suite (`pytest tests/ -x -q`) — zero regressions is the bar,
especially `test_multistage_config.py`, `test_dump_enqueue.py`,
`test_parallel.py`, `test_node_selection.py`.

## Docs

- `docs/usage_guide.md` §14g: replace the "deliberately restricted" paragraph;
  add sweep×stages, `--enqueue` batching, and the one-job-per-item resource
  limitation. §6 sweeps: `--sweep`+`--enqueue`. §9 HPC: pipeline example.
- `docs/cli_reference.md`: update `--select`, `--enqueue`, sweep interactions.
- `--select` argparse help string in `runner.py`.

## Commit discipline

Commit per phase on the `pipeline-tasks` branch (worker → api → runner →
dequeue → enqueue-sweep → docs), each with green tests. Do not touch `main`.
