# Dev plan: run records, presets, run references, subtree swaps

Status: proposed (2026-09-24). Branch base: `env-fingerprint`.

Goal: make **presets** (the `-d module.attr -s key` you run) and **runs** (the
directories they produce) first-class, named, linkable objects, and make the
run directory the complete record again, including for Slurm and sweeps.
`flexlock-run` keeps its current interface; everything here is additive.

Phases are independent PRs, in order. Each lists the files touched and the
tests that gate it.

---

## Phase 0 — Fix: sweep/HPC tasks lose git provenance (done)

**Bug.** The sweep master `run.lock` (`parallel.py`) found repos through
`extract_tracking_info(self.cfg)`, which auto-detects them from the *base*
config's `_target_`. Workers snapshot each task with `repos=None` and rely on
the master through `parent`. When `_target_` lives in the task instead of the
base, nobody recorded the code state:

- single-run Slurm/PBS submissions (the whole config is the one task);
- `--sweep-file` of full configs, i.e. the enqueue → drain workflow.

Observed: `sst_ml_zarrpatch/results_starter_glob/train_small_cloud_gap_compact_0002`
has a master `run.lock` with only `save_dir` + empty `_snapshot_`, and a task
snapshot with `config, fingerprint, parent, timestamp`. No tree and no commit
anywhere. Parameter sweeps (base carries `_target_`) were unaffected.

**Which tree is "the code that ran"?** Neither submit time nor worker time is
exact. Python loads a module at first import, so an edit made while a job waits
in the queue, or before a lazy import, runs code no submit-time tree describes;
an edit made after the import changes the tree but not the running code. So:

1. **Record at submit.** `utils.collect_task_repos` adds the repos of each
   distinct task `_target_` to the master snapshot, one merge per distinct
   target, not per task. Same semantics parameter sweeps already had.
2. **Detect drift at the end of the run.** `git_utils.code_drift(repos, since)`
   checks every module in `sys.modules` whose file is in a recorded repo and
   was modified after the snapshot. It uses mtime as a pre-filter, then compares
   the file's git blob hash against the recorded tree; a new, non-ignored file
   also counts. Results go under `code_drift: {repo: [paths]}`:
   - sweep tasks: in the task's DB snapshot, written inside the existing
     batched `finish_tasks` transaction (`snapshot=COALESCE(?, snapshot)`), so
     there's no extra write;
   - serial runs: appended to `run.lock` (`snapshot.record_code_drift`).
   `flexlock diff` prints a warning when either run has drift. The record never
   claims more than it knows: "this tree, except these files, whose loaded
   version is uncertain".

Tests: `tests/test_code_drift.py` (touch without change, edit of a loaded vs
unloaded module, new vs ignored file, task-repo collection, single-task sweep
records master repos, edit during a task, serial `run.lock`).

## Phase 0b — Frozen code (opt-in, later)

`--freeze-code`: at submit, check out the shadow commit (already created per
run) into `.flexlock/code/<tree>/`, shared by all runs with that tree. Workers
put it first on `PYTHONPATH`, ahead of the editable install, so what ran is
exactly the recorded tree and you can keep editing while jobs sit in the queue.
Costs one checkout per distinct tree; the SIF bind-mount must include
`.flexlock/`. It covers Python code in tracked repos, not data files the code
reads through relative paths.

## Phase 1 — Run records: one place per run, one reader (done)

### 1a. Write the full record into the task dir (default)

New option `task_record = "dir" | "db"`, default `"dir"`:

- `Project.submit(..., task_record=None)`, CLI `--task-record {dir,db}`, env
  `FLEXLOCK_TASK_RECORD`. It's never inferred from the sweep source; `--sweep-file
  paths.txt` stays `dir` unless you ask for `db`.
- `dir`: the worker writes `run.lock` into the task's `save_dir` with the
  **materialized** record: master `repos`/`env` inlined + task
  `config`/`fingerprint`/`timestamp`/`note` + `parent` kept as a pointer. The
  DB `snapshot` column is still filled (the queue stays self-describing).
- `db`: today's behaviour (marker + DB snapshot only).
- Single-run HPC case: task `save_dir` == master dir. The full record
  **replaces** the master stub. A dir is still recognized as a sweep master by
  the presence of `run.lock.tasks.db`, so `query.run_status` precedence is
  unchanged.
- `.flexlock_marker` is written in both modes (status lookups stay cheap).

Files: `worker.py`, `api.py` (`submit`, `_submit_sweep` plumbing),
`parallel.py`, `runner.py` (flag), `backends/*` (pass-through to worker CLI),
`worker_cli.py`.

### 1b. One reader: `flexlock/record.py`

```python
def load_record(run_dir) -> dict | None
    # 1. run.lock that is a full record  → return it
    # 2. .flexlock_marker                 → DB snapshot for task_id, materialized
    #                                       with the master run.lock it points to
    # 3. run.lock stub + run.lock.tasks.db (single-task master) → that task's record
    # 4. None
def iter_records(root) -> Iterator[tuple[Path, dict]]
    # walks run.lock AND .flexlock_marker dirs; yields each run exactly once
```

Side-effect free (`yaml.safe_load`, never resolves interpolations; same
constraint as `query.py` today).

Migrate every consumer onto it:

| Consumer | Today | After |
|---|---|---|
| `diff_cli.load_snapshot` | `run.lock` only | `load_record` |
| `api._glob_scan_match` (cache fallback) | `**/run.lock` | `iter_records` |
| `snapshot._find_snapshot_dir` (lineage `prevs`) | `run.lock` only | `load_record` |
| `resolvers.run_lock_resolver` | `run.lock` only | `load_record` |
| `query` show/graph/why | own marker logic | `load_record`/`iter_records` |
| `cli reindex`, `export` | `run.lock` | `iter_records` |

Tests: a matrix of {serial, param sweep, single HPC task, sweep-file of full
configs} × {dir, db}. For each, `flexlock diff A B`, cache fallback hit,
lineage via `prevs`, `${run_lock:}` and `flexlock show` all see the same record.

### As built (notes)

- `task_record` is stored in the master `run.lock` (`snapshot(meta=...)`), so
  workers attached later with `flexlock-worker` follow it without CLI
  plumbing; masters written before this change have no key and keep DB-only.
- A dir-mode task writes `run.lock` only if the dir has none, holds its own
  record (rerun), or holds the master stub of a single-task sweep. Tasks that
  share one `save_dir` never clobber each other; the first keeps the file.
- Task records carry `task_id` and `code_timestamp` (the master's snapshot
  time, used by the drift check once a single-task record replaces the stub).
- The collision guard skips dirs with a `.flexlock_marker`: they are resumed
  through the task DB, as before task dirs carried a `run.lock`.
- `gc` keeps anything inside or containing a protected (tagged or lineage)
  path, and `gc --incomplete` never prunes tasks the DB reports running or
  pending.
- `record.read_lock` keeps timestamps as strings (as `OmegaConf.load` did):
  plain `yaml.safe_load` returns `datetime`, which OmegaConf rejects.

## Phase 2 — Presets (done)

### Definition

A preset is the address you already give on the command line: the `-d` target
plus the `-s` key. Nothing is discovered or registered; `load_python_defaults`
already resolves it. Canonical address:

- dotted: `sst_ml_mapping.starter.xps_glob:train_small_cloud_gap_compact`
  (module `:` attribute, normalized from the `a.b.c` form);
- file: `configs/defaults.py:defaults`, path relative to the repo root.

### Recording

A reserved config key, `_preset_`, set on the selected node:

```yaml
_preset_:
  defaults: sst_ml_mapping.starter.xps_glob:train_small_cloud_gap_compact
  select: main
  overrides: ["main.lit_module.lr=1e-4"]        # -o/-O as typed, in order
  merges: []                                     # -m/-M files
```

It's a config key (like `_snapshot_`) rather than run metadata, so it travels
unchanged through pickling, the task DB, HPC workers and sweeps without new
plumbing. Sweep items inherit it.

- Set by `runner.run` (CLI) and by `Project.get(key)` / `Project.submit("key")`
  when `Project` was built from an import string (`defaults_str`). A raw-dict
  `Project` or config sets nothing.
- Excluded from the fingerprint (`fingerprint._TRACKING_KEYS`), from
  `RunDiff` (`always_ignore`), and stripped by `instantiate` (same code path as
  `_snapshot_`). A run's cache identity does not depend on which preset
  produced it.
- `flexlock diff` prints preset differences as information, not as a mismatch.

### Preset links

On completion (`api.py` single-run path after `mark_complete`, and in the
worker after a task finishes), if the config has `_preset_`, create:

```
<project>/.flexlock/presets/<defaults>/<select>/<save_dir basename> -> <save_dir>
```

`<project>/.flexlock` is the same root as the fingerprint index
(`index.resolve_index_path`, `$FLEXLOCK_INDEX` override). Symlink creation is
atomic and needs no locking. `flexlock reindex` rebuilds links from
`iter_records`. The `project_template` gets a `.flexlock/` at its root.

### CLI

- `flexlock runs <address> [-s main] [--all] [--format json]`: runs of a
  preset, newest first, with status, timestamp, note and overrides. Suffix
  match on the address (`xps_glob:train_small_cloud_gap_compact` is enough);
  an ambiguous suffix is an error listing the candidates.
- `flexlock presets <module>`: config-valued attributes of a module, each with
  its leading comment block. It's a generated replacement for hand-written
  catalogues like `maxss_configs/index.md`, including a run count per preset
  from the links.

Files: `runner.py`, `api.py` (`Project.get/submit`), `utils.instantiate`,
`fingerprint.py`, `diff.py`, `worker.py`, new `presets.py` (address
normalization + links + lookup), `cli.py`.

Tests: address normalization (dotted, `a.b:c`, file forms); `_preset_` never
changes the fingerprint; links created for serial, sweep and HPC-task runs;
`reindex` rebuilds them; `flexlock runs` ordering and suffix ambiguity.

### As built (notes)

- `_preset_` goes only on runnable nodes (`_target_` + `save_dir`), the same
  definition `flexlock presets` uses, so `proj.get("params")` or a model
  sub-config never gains a key. It is stripped from the fingerprint at any
  depth.
- Overrides are stored as typed but escaped (`\${`), so an override such as
  `-o 'train_dir=${run:...}'` stays text inside `_preset_`. This exposed a
  general bug: `resolve_deferred` re-wrapped resolved values, turning any
  escaped literal back into a live interpolation; it now re-escapes.
- Link names are the save_dir relative to the project (`results__xp1__train`):
  the `pipeline_dir` pattern gives many runs the same basename.
- Index location: the walk-up now stops at any existing `.flexlock/` dir
  (not only one holding `index.db`), so a project-level `.flexlock/` (the
  template creates one) serves every results dir. Existing per-results-dir
  indexes are still found first. `flexlock runs` also scans `*/.flexlock` and
  `*/*/.flexlock` below the current dir.
- `flexlock presets` counts stages at the attribute's top level or one level
  down; deeper nodes with a `save_dir` (e.g. a Lightning callback) are
  building blocks. Checked on `sst_ml_mapping.starter.xps_glob`: 60+ presets
  listed with their comment blocks.
- Runs made before this phase have no `_preset_`; `reindex` cannot infer one.
- Not done: `@flexcli` scripts (no `-d`) record no preset.

## Phase 3 — Run references: `${run:...}` (done)

```
${run:<address>,<select>}           latest complete run of the preset
${run:<address>,<select>,<pin>}     pinned: the run whose dir basename ends with <pin>
```

Example, replacing `_default_train = "results_starter_glob/train_small_cloud_gap_0000"`:

```python
infer_cloud_gap = dict(
    train_dir="${run:xps_glob:train_small_cloud_gap,main}",
    main=py2cfg(infer_fn, xp_path="${train_dir}", ...),
)
# CLI pin:  -o 'train_dir=${run:xps_glob:train_small_cloud_gap,main,0005}'
# checkpoint: "${run:xps_glob:vae,main}/checkpoints/best_model.ckpt"
```

- **Any run of the preset matches by default**, whatever its overrides. A
  4th argument `strict` restricts matches to runs with no overrides.
- **Complete runs only.** Pins also require complete runs; a pin that exists but
  isn't complete is an error that says so.
- **Resolved at submit time**, so `--print-config`, `--dump`, `--enqueue` and
  `run.lock` all show the concrete path, and the fingerprint sees it. This
  differs from `${latest:}`/`${run_lock:}`, which are deferred.
- **Lineage:** every resolved reference is appended to the run's `prevs`, so
  `flexlock graph` draws the edge without a hand-written `_snapshot_.prevs`.
- Lookup: preset links first; if there are none, fall back to scanning
  `iter_records` under the search roots and backfill the links.
- Resolver arguments are comma-separated because OmegaConf splits resolver args
  on commas; `:` inside an argument is allowed.

Files: `resolvers.py`, `presets.py`, `freeze.py` (keep `run` out of the deferred
set; confirm the freeze pass resolves it), `utils.extract_tracking_info` (add
prevs).

Tests: latest vs pin vs strict; incomplete and failed runs skipped; missing
preset error message; the reference appears in `prevs`; the resolved path is in
`--dump` output.

### As built (notes)

- `presets.freeze_run_refs(cfg)` resolves only values containing `${run:`
  (other flexlock resolvers stubbed, other interpolations untouched), so
  `${.save_dir}/logs` still follows `--save-dir-policy increment`. Called by
  the runner right after selection (so `--dump`, `--enqueue`, `--edit-config`
  see the concrete run), by `Project.submit` (no-op if already done, covers the
  Python API and single HPC runs), and per sweep item before the sweep freeze.
- `Project.get` keeps `${run:}` as a call string (the selection freeze stubs
  every flexlock resolver, `run` included); `submit` resolves it.
- Lineage: resolutions inside `freeze_run_refs` are collected and appended to
  the config's `_snapshot_.prevs` (never part of the fingerprint).
- `strict` is accepted as the 3rd argument (`${run:x,main,strict}`): an empty
  pin (`,,strict`) makes OmegaConf warn.
- Debug runs: make them their own preset (`train_x_debug`); address matching
  is anchored on the full attribute name, so `train_x` never matches it.

## Phase 4 — Subtree swap by name: `@attr`

```
flexlock-run -d sst_ml_mapping.starter.xps_glob.train_small_cloud_gap -s main \
    -o main.lit_module.model=@small_model_tw15
```

- A `-o`/`-O` value starting with `@` is looked up as an attribute of the
  `-d` module, then as a fully qualified `@pkg.mod.attr`. `@@` escapes a
  literal `@`. A failed lookup is an error listing the module's config-valued
  attributes.
- **Replaces** the node (Hydra config-group semantics); it doesn't merge. A merge
  would leave stale keys from the old model.
- Works in sweeps: `--sweep "@small_model,@big_model" --sweep-target
  main.lit_module.model`. Items are expanded in `load_sweep` on the submitting
  side, so workers never import the config module to resolve names.
- Recorded as typed in `_preset_.overrides`; the expanded subtree is in
  `config`, so provenance is complete.
- This replaces ad-hoc resolvers such as `${sel_model:}` in `xps_glob.py`.

Files: `runner.py` (`load_config`, `_flatten_overrides`), `utils.load_sweep`,
`api.Project.submit` (dict `overrides` accept `@` too).

Tests: root and after-select overrides; replace-not-merge; fully qualified
fallback; escape; sweep expansion; error listing.

## Phase 5 — Later (separate plan)

Symlink key index replacing `index.db`, extracting the fingerprint + store core
with no OmegaConf dependency, and splitting `Project.submit` into cache /
sweep / backend option groups. The preset links above use the same symlink
approach, so this phase generalizes a mechanism already proven in Phase 2.

## Docs and template

Per phase: `usage_guide.md`, `cli_reference.md`, `hpc_integration.md` (task
records), and the shipped skills (`flexlock-survey` uses `flexlock runs` and
`presets`). `project_template/docs/workflow.md`: replace copied versioned paths
with `${run:}`, add `.flexlock/` at the project root, mention `@attr`.

## Open questions

- Should `${run:}` also accept `flexlock tag` names (`${run:@best_vae}`)? Tags
  already exist (`cli.cmd_tag`); one lookup path for both seems natural.
- `flexlock presets` needs module import; for heavy modules (torch at import),
  do we accept that cost or parse source with `ast` for the comment blocks?
