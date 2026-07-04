# FlexLock — Implementation plan for `fable_notes.md`

Worktree: `/scale/user/qfebvre/projects/2509_flexlock/flexlock_fable`
Branch: `fable-improvements` (off `main` @ a6d25d3)
Test runner: `pixi run test` (pytest, suite under `tests/`)

All findings in `fable_notes.md` were re-verified against current `main`; every issue
is still present. Work is grouped into 5 phases ordered by **risk-adjusted value**:
surgical correctness fixes first (small, well-tested, high impact), then the two
structural refactors that eliminate whole bug classes, then docs, then the optional
deep redesigns.

Each item lists: **change**, **files**, **test**. Commit per item (or per tight
group) so review and bisection stay clean.

---

## Phase 0 — Guardrails (do first, ~30 min)

Before touching behaviour, lock in the current contract so regressions are visible.

1. **Baseline the suite.** `pixi run test` on the fresh worktree; record pass/fail so
   we distinguish pre-existing failures from ones we introduce.
2. **Add characterization tests for the caching path** — a serial single-run cache-hit
   (via `_find_matching_run`), and a `n_jobs=2` sweep re-run. The sweep re-run **already
   works** via the task DB (`INSERT OR IGNORE` + `pending_count`); the test pins that
   behaviour so the Phase 2.2 re-scoping doesn't regress it. (This corrects the earlier
   "issue 1 = resume broken" premise — resume is fine; see 2.2.)

No production code changes in this phase.

---

## Phase 1 — Surgical correctness fixes (low risk, isolated)

These are localized, each independently testable, no cross-dependencies. Land them
first to bank value and shrink the diff the refactors sit on top of.

### 1.1 `hash_data(use_cache=False)` ignored — **issue 4**
- **Change:** replace the hand-rolled `os.environ.get("FLEXLOCK_NO_CACHE", use_cache)
  not in (...)` with: honour the `use_cache` argument, and let the env var only *force
  off* — `use_cache = use_cache and not config.get_env_bool("FLEXLOCK_NO_CACHE", False)`.
- **Files:** `flexlock/data_hash.py` (import `from . import config`).
- **Test:** `tests/test_data_hash.py` — assert `use_cache=False` recomputes (patch
  `_get_db` to fail if opened); assert `FLEXLOCK_NO_CACHE=1` disables even when
  `use_cache=True`; assert `yes`/`on` accepted.

### 1.2 `dirhash` ignores file paths — **issue 5**
- **Change:** hash `(relative_path, content_hash)` pairs, not bare content hashes.
  Build `rel = f.relative_to(base_path).as_posix()`, feed `f"{rel}\0{content_hash}"`
  into the final hasher over the sorted list.
- **Files:** `flexlock/data_hash.py` (`dirhash`).
- **Compat note:** this changes directory hash values → **invalidates existing data
  caches and any stored `run.lock` data hashes**. Acceptable (hashes are opaque), but
  call it out in CHANGELOG; bump an internal hash-version constant so stale cache rows
  are ignored rather than mismatched. Clear `~/.cache/flexlock/hashes.db` is the manual
  fallback.
- **Test:** `tests/test_data_hash.py` — two dirs with identical file contents under
  different names must now hash differently; swapping contents between two files must
  change the hash.

### 1.3 `git_utils` returns error strings — **issue 13**
- **Change:** `get_git_tree_hash` / `get_git_commit` raise (wrap in
  `FlexLockSnapshotError`) instead of returning `f"Error ..."`. Grep callers first —
  if any rely on the string-return being truthy, adjust to try/except.
- **Files:** `flexlock/git_utils.py`, `flexlock/exceptions.py` (already has the class),
  callers found via grep.
- **Test:** `tests/test_git_utils.py` — calling on a non-repo path raises, not returns
  a string.

### 1.4 `instantiate` mutates its input — **issue 11**
- **Change:** copy the config **before** `del cfg["_snapshot_"]`. Move the defensive
  copy to the top of `instantiate` so the caller's config keeps `_snapshot_`.
- **Files:** `flexlock/utils.py` (`instantiate`, ~line 838).
- **Test:** `tests/test_utils.py` — instantiate a cfg with `_snapshot_`, assert the
  original still has the key afterward.

### 1.5 Env-var parsing drift — **issue 10**
- **Change:** route `FLEXLOCK_DEBUG` parsing in `flexcli.py` and `runner.py` through
  `config.get_env_bool`; delete the ad-hoc `in ("1","true")` checks.
- **Files:** `flexlock/flexcli.py`, `flexlock/runner.py`, `flexlock/debug.py` (make it
  read `config.DEBUG_STRATEGY` instead of `os.environ.get` directly).
- **Test:** `tests/test_flexcli.py` / `test_debug_*` — `FLEXLOCK_DEBUG=yes` enables.

### 1.6 `latest:` resolver returns the pattern on no-match — **issue 20**
- **Change:** raise `FileNotFoundError` when no match; add optional `default` arg
  mirroring `run_lock:`. Replace `run_lock:`'s `default=None` sentinel with a distinct
  `_MISSING` sentinel so an explicit `null` default is honoured.
- **Files:** `flexlock/resolvers.py`.
- **Test:** `tests/test_resolvers.py` — no-match raises; with default returns default;
  explicit `null` default distinguishable from absent.

### 1.7 `vinc:` concurrency — **issue 19**
- **REVISED after implementation:** the mkdir-in-resolver claim is **incompatible**
  with load-bearing behaviour. `${vinc:}` must resolve *idempotently* for multiple
  references within one `submit()` (save_dir, logger_dir, dirpath all frozen to the
  same `${vinc:}` node by `select_and_freeze_root_refs`); the codebase coordinates
  versioning purely through filesystem scans, and the counter only advances once the
  previous run's dir exists. Claiming a dir on *every* resolver call makes the 2nd/3rd
  reference advance (breaks `test_vinc_stable_with_cross_tree_refs`).
- **Done instead:** keep pure-scan; document the residual cross-process race in the
  docstring. The atomic claim is **deferred to the run-commit path** (Phase 3.1
  `RunRecord`: create the dir with `exist_ok=False` + retry), which is the only place
  a claim can be taken without breaking within-submit idempotency.
- **Files:** `flexlock/resolvers.py` (docstring).

### 1.8 Dead / broken code — **issue 17**
- **Change:** delete `FlexLockRunner.check_if_exists` (broken, uncalled); remove the
  unreachable `if self.defaults is None` in `Project.get`; simplify
  `return None if return_snapshot else None` in `snapshot.py`. For `STRICT_VALIDATION`
  / `MAX_DISPLAY_ITEMS`: **delete** from `config.py` and the env-var doc table (nothing
  reads them; implementing them is out of scope).
- **Files:** `flexlock/runner.py`, `flexlock/api.py`, `flexlock/snapshot.py`,
  `flexlock/config.py`, `docs/reference.md`.
- **Test:** existing suite must stay green; grep confirms no references.

### 1.9 Logging stack split — **issue 18**
- **Change:** in `taskdb.py` drop the `logging.getLogger(__name__)` shadow; use the
  loguru `logger` already imported, consistent with the rest of the package.
- **Files:** `flexlock/taskdb.py`.
- **Test:** smoke — a `dump_to_yaml` collision path emits via loguru (capture with
  `caplog`/loguru sink).

**Phase 1 exit:** full suite green; each fix has a dedicated test.

---

## Phase 2 — Cache & result correctness (the core-promise fixes)

These are the issues the notes call out as most important (1–3), plus the diff-quality
issues that share the same code. Slightly higher risk; sequence matters.

### 2.1 Fingerprint as a pure, stable digest — **issue 3 + redesign 3 (part 1)**
- **Change:** add `create_shadow_tree(repo_path, ignore_patterns)` in `git_utils.py`
  that stages into a shadow index and runs **`write-tree` only** (no `commit-tree`, no
  `update-ref`), returning `{tree, is_dirty}`. Keep `create_shadow_snapshot` (commit+ref)
  for the real execution path. Add a `persist: bool` flag to `RunTracker.record_env`
  (default `True`); fingerprinting calls it with `persist=False` -> tree-only, so
  smart-run leaves no refs/commits behind.
- **Produce a `Fingerprint` value:** `fingerprint(cfg) -> str` = stable digest (sha) over
  (a) canonicalized config with `save_dir` **prefix-normalized at fingerprint time**,
  (b) per-repo tree hashes, (c) data hashes. Where include/exclude patterns are set,
  hash the **filtered subtree** (git tree restricted to the pathspec) so today's
  "relevant-files-unchanged still matches" becomes plain digest equality — no special
  case in the matcher.
- **Files:** `flexlock/git_utils.py`, `flexlock/snapshot.py`, new
  `flexlock/fingerprint.py`, `flexlock/api.py`.
- **Test:** `tests/test_git_utils.py` — `create_shadow_tree` adds **no** `refs/flexlock/
  runs/*` and no commit object, same `tree` as `create_shadow_snapshot`.
  `tests/test_fingerprint.py` (new) — same cfg -> same digest; changing an
  include-relevant file changes it; changing an excluded file does not; save_dir change
  alone does not.

### 2.2 Project-wide fingerprint index — sweep items first-class — **issue 1 (DECIDED: first-class) + redesign 3 (part 2)**
- **Decision recorded:** sweep items **must be first-class** — a config first run as a
  sweep task must cache-hit when re-run serially or from a different sweep, and be
  discoverable as `prevs` lineage and in `flexlock ls/diff`. (Correction to the note:
  same-*sweep* resume already works via the task DB's `INSERT OR IGNORE` + `pending_count`
  early-return; that is **not** the gap. The gap is that a sweep task's snapshot lives
  only in the DB, invisible to every `run.lock` reader.)
- **Change:** introduce a derived, project-wide index (SQLite,
  `<results_root>/.flexlock/index.db` — location resolution below):
  ```
  runs(fingerprint PK, status, location_kind, run_lock_path,
       task_db_path, task_id, save_dir, ts)
  ```
  - On **any** successful run — serial *or* sweep task — upsert a row keyed by
    `fingerprint` with `status='done'` and a location pointer:
    `location_kind='run_lock'` -> `run_lock_path` (+ `save_dir`), or
    `location_kind='task'` -> `task_db_path` + `task_id` (+ `save_dir`).
    Serial/isolated/single-HPC writes go through `api.py`; sweep tasks write from
    `worker.py` right after `write_complete_marker`.
  - `_find_matching_run` becomes: `fp = fingerprint(cfg)` -> `SELECT ... WHERE
    fingerprint=? AND status='done'`. On hit, **verify** the pointed-to location still
    exists and is complete (`run.complete` for run_lock; task row still `done` +
    `results.json` present for task); if stale, **prune the row and treat as miss**
    (self-healing). This subsumes the current `run.complete`-exists check and, because
    only `status='done'` rows are returned, failed/interrupted runs are never served
    from cache (ties into 2.3).
  - `get_result` resolves either location kind to the right `results.json` (or the task
    row's `result_info`) uniformly.
- **Index-location resolution:** the index must be shared across the runs it should
  match. Resolve in order: `FLEXLOCK_INDEX` env -> nearest `.flexlock/index.db` walking
  up from each `search_dir` -> a per-`search_root` `.flexlock/index.db`. Document that
  `search_dirs` and the index scope must agree (a project-level wrapper should set both).
- **Legacy backfill & fallback:** the index is a **derived cache**; `run.lock` stays
  authoritative. Add `flexlock reindex <dir>` to walk existing `**/run.lock` once and
  populate the index. On an index **miss**, optionally fall back to the old glob scan
  (behind `FLEXLOCK_INDEX_FALLBACK=1`, default on for one release) and backfill any hit
  so the slow path self-eliminates. Removing the index file is always safe.
- **Concurrency:** many sweep workers upsert concurrently — reuse the taskdb SQLite
  conventions (`busy_timeout`, `INSERT OR REPLACE` by PK). Upsert-to-`done` is
  idempotent; a later success for the same fingerprint just refreshes the pointer.
- **RunDiff:** demoted to the **explainer** for `flexlock-diff` only (human-readable
  "why different"), no longer the matcher.
- **Files:** new `flexlock/index.py`, `flexlock/api.py` (`_find_matching_run`,
  `get_result`, write-on-success), `flexlock/worker.py` (write-on-success),
  `flexlock/cli.py` (`reindex`), and `RunRecord` (Phase 3.1) as the natural writer.
- **Test:** `tests/test_index.py` (new) — a config run as a sweep task is a cache hit
  when re-submitted serially; a failed task is **not** a hit; deleting the pointed-to
  dir makes the stale row self-prune to a miss; `reindex` backfills legacy `run.lock`
  runs; a 100-item sweep re-run does **not** re-parse every old `run.lock` (assert the
  glob path isn't taken when the index is warm).

### 2.3 Failures reported as SUCCESS — **issue 2** (+ **14**, **16** structurally)
- **Change:** introduce a single `collect_results(indices, configs, db_path, tag)` that
  reads per-task terminal status from the task DB (`get_all_tasks`/`get_status_counts`
  by task id) and builds `ExecutionResult` with real statuses
  (`SUCCESS`/`CACHED`/`FAILED`/`INTERRUPTED`/`SUBMITTED`) and `error`. Replace the four
  hand-built `status="SUCCESS"` sites (single-HPC, isolated, sweep-parallel,
  and the missing-`results.json`→`None` case) with calls to it.
- **Also (issue 14):** add `timeout: int | None = None` param to `Project.submit`
  (default `None`); thread it to both the single-HPC and sweep waits so behaviour is
  consistent and user-controllable. Remove the asymmetric `DEFAULT_TIMEOUT`-vs-`None`
  split.
- **Also (issue 16):** forward `isolated` and `debug` into `_submit_sweep`; where a
  path genuinely can't honour a kwarg, raise `FlexLockConfigError` rather than silently
  dropping it.
- **Files:** `flexlock/api.py` (new helper + call sites), `flexlock/taskdb.py`
  (ensure a `get_all_tasks`/status-by-id accessor exists).
- **Test:** `tests/test_parallel.py` / `test_api.py` — a sweep where one task raises
  returns that item with `status="FAILED"` and a non-empty `error`;
  `max(results, key=...)` can skip failures. HPC path mocked.

### 2.4 `force=True` reaches sweep items — **issue 15**
- **Change:** move the `run.complete` invalidation to *after* per-item merge — unlink
  each item's `save_dir/run.complete` inside `_submit_sweep` when `force`. Thread a
  `force` flag into `_submit_sweep` (currently not passed).
- **Files:** `flexlock/api.py`.
- **Test:** `tests/test_submit_params.py` — a forced sweep re-executes every item even
  when markers exist.

### 2.5 RunDiff correctness — **issues 7, 8, 9**
- **7 (ignore list eats user keys):** stop ignoring `date/time/system/cwd/job_id/
  work_dir/datetime` at *every* nesting level. Apply the ignore set **only at the
  snapshot top level** (the keys FlexLock itself injects), not inside the user
  `config` subtree. Implement by passing `depth`/`path` to `_recursive_diff` and only
  honouring the FlexLock-injected keys at `path == ""`. (`save_dir`/`_snapshot_` stay
  normalized/ignored as today.)
- **8 (substring normalization):** in `_normalize_val`, replace only a path *prefix*:
  `if val == root or val.startswith(root + os.sep): val = "<SAVE_DIR>" + val[len(root):]`.
- **9 (asymmetry / thin messages):** iterate the union of `c_repos`/`t_repos` keys in
  `compare_git` (flag repos present in target but not current); make `compare_data`
  report which keys/hashes differ instead of `"Data differs"`.
- **Files:** `flexlock/diff.py`.
- **Test:** `tests/test_diff.py` — user key `train.time: 100` vs `200` is a mismatch
  (not ignored); `outputs/other/data.csv` is not spuriously normalized when `save_dir`
  is `outputs`; a repo only in target is flagged; data diff names the key.

**Phase 2 exit:** the sweep-resume characterization test passes; failed sweep items are
visible; smart-run leaves no git refs behind; diff tests cover the false-hit cases.

---

## Phase 3 — Structural refactors that kill bug classes

Two focused refactors from the "deeper redesign" list. These are worth doing because
Phase 2 fixes (esp. 2.2, 2.3) are cleaner on top of them; do them if the Phase 2 interim
versions feel fragile.

### 3.1 `RunRecord` — one owner of the on-disk contract — **redesign 2**
- **Change:** a class encapsulating a run directory: `write_lock(snapshot)`,
  `mark_complete(result)`, `write_results(result)`, `load()`, `status` property,
  `is_complete`, and — on `mark_complete` — **upsert the fingerprint index row** (2.2)
  so the index write happens in exactly one place for serial runs *and* sweep tasks.
  `RunTracker.save`, `worker.py`, and the `api.py` single-run path all route through it.
  This makes driver and worker structurally identical (the reason issue 1's fix is
  clean here) and gives `flexlock ls/gc/diff` and the index a single loader/writer.
- **Files:** new `flexlock/run_record.py`; refactor `snapshot.py`, `worker.py`,
  `api.py`, `cli.py`.
- **Test:** new `tests/test_run_record.py` (round-trip lock/complete/results/status);
  existing snapshot/cli tests must stay green.

### 3.2 `ExecutionResult` as a typed result — **redesign 5** (+ fixes **issue 6**)
- **Change:** frozen dataclass with a `Status` enum, `error: str | None`,
  `metrics: dict` (the return payload), `.get`/`__getitem__` delegating to `metrics`.
  **Remove** the `setattr(self, key, value)` dynamic-attribute injection (issue 6 —
  clobbering). Add `raise_on_failure()`. Keep `.result`/attribute-style access via an
  explicit `__getattr__` over `metrics` for backward compat (documented, and guarded
  against reserved names).
- **Compat risk:** `submit_chained` reads `getattr(parent, attr)` (e.g. `save_dir`) —
  ensure those remain real attributes. `runner.run` unwraps `.result`.
- **Files:** `flexlock/api.py`.
- **Test:** `tests/test_api.py` — a function returning `{"status": "...", "get": 1}`
  no longer clobbers `ExecutionResult.status`/`.get`; `raise_on_failure` raises on
  `FAILED`.

> **Deferred (document as follow-up issues, do not implement now):**
> - **redesign 1** (split the `submit` god-method into `ConfigPipeline` +
>   `ExecutionBackend` protocol + `collect_results`): large; Phase 2.3 already extracts
>   `collect_results`, which is the highest-value slice. Full backend-protocol refactor
>   is a separate PR.
> - **redesign 3** (project-wide fingerprint index): **promoted into Phase 2.1/2.2** —
>   it is the mechanism that makes sweep items first-class, so it is no longer deferred.
> - **redesign 4** (replace hand-rolled interpolation parser with OmegaConf grammar):
>   high-risk, needs property-based tests; only worth it if freeze bugs surface.
> - **redesign 6** (functional `submit_chained` without `self.defaults` mutation) and
>   **redesign 7/8** (exception wrapping, `Settings` dataclass): schedule after the
>   above land.

---

## Phase 4 — Documentation & guidelines

Land alongside the code so docs match reality.

1. **Fix every doc↔code mismatch** from the notes table: CLI caching is opt-in
   (`--check-exists`); `flexlock diff` is the separate `flexlock-diff` entry point;
   default save_dir fallback is `outputs/<name>/<timestamp>`; `sweep_dir_suffix`
   *nests* `sweep_{i:04d}`; `ExecutionResult` statuses; unify the
   `FLEXLOCK_DIR_FILE_LIMIT` vs `FLEXLOCK_CACHE_DIR_FILE_LIMIT` knob to one name;
   correct `FLEXLOCK_CACHE` default to `~/.cache/flexlock`; either implement or delete
   the `FLEXLOCK_CONFIGURE_LOGGING` behaviour and the exception-wrapping claim in §12.
   - **Files:** `README.md`, `docs/quickstart.md`, `docs/reference.md`,
     `docs/usage_guide.md`, `Project.submit` docstring, `ExecutionResult` docstring.
2. **Add the 10 usage guidelines** from the notes to `docs/usage_guide.md` (canonical
   results root + explicit `search_dirs`; spell caching intent; check `run.complete`
   before trusting results; keep targets importable / not in notebooks; `.gitignore`
   big files + periodic `flexlock gc`; relative-interp-only configs; one sweep = one
   dir + `tag=`; `dry_run` before HPC; small JSON-serializable returns avoiding reserved
   keys; avoid reserved config key names).
3. **Document the shadow-snapshot storage cost** (`git add --all` commits un-ignored
   files into `.git`) prominently in `docs/philosophy.md` / snapshot docs.

Some guideline items become *unnecessary* once code is fixed: guideline 3 ("don't trust
result.status") is handled once the index serves only `status='done'` runs (2.2) and
statuses are real (2.3); guideline 10 (reserved config key names) after issue 7. Reframe
those as "now handled" rather than warnings.

---

## Sequencing summary

```
Phase 0  baseline (done: 407 green) 
Phase 1  1.1 1.2 1.3 1.4 1.5 1.6 1.7 1.8 1.9        (DONE, 415 green)
Phase 2/3 interleaved [DECIDED]:
         2.1 pure Fingerprint digest
         3.1 RunRecord (single on-disk-contract owner + sole index writer)
         2.2 project-wide index (sweep items first-class, via RunRecord)
         2.3 real statuses (collect_results) -> feeds 2.2 status
         2.4 force reaches sweep items
         2.5 RunDiff correctness (explainer only)
         3.2 ExecutionResult typed dataclass
Phase 4  docs + guidelines                          (last, matches shipped behaviour)
```

Each phase ends green on `pixi run test`. Recommend a PR per phase (Phase 1 as one PR
of small commits; Phase 2 as its own; Phase 3 optional separate PR).

## Explicit decisions — RESOLVED
- **2.2 sweep items first-class** via the project-wide fingerprint index (redesign 3).
  - **Index location scope [DECIDED]:** resolve in order (1) `FLEXLOCK_INDEX` env,
    (2) nearest `.flexlock/index.db` walking up from each `search_dir`, (3) per
    results-root `<results_root>/.flexlock/index.db`. A project wrapper should set both
    `search_dirs` and the index so they agree.
  - **Sequencing [DECIDED]:** interleave — **Phase 3.1 `RunRecord` lands before 2.2**
    so the index has exactly one writer for serial runs *and* sweep tasks. Order:
    `2.1 fingerprint -> 3.1 RunRecord -> 2.2 index -> 2.3 statuses -> 2.4 -> 2.5 -> 3.2`.
  - **Glob fallback lifetime:** keep `FLEXLOCK_INDEX_FALLBACK` (default on) for one
    release so legacy runs still hit + backfill, then default off.
  - **Task-row git identity:** include the master snapshot's `repos` in a task's
    fingerprint (else `parent_lock` short-circuits git and the fingerprint
    under-specifies code identity).
- **1.2 hash format change [DONE]:** accepted invalidating existing data-hash caches;
  implemented via `HASH_VERSION` bump + versioned cache file (`hashes_v2.db`).
- **1.7 vinc claim [REVISED]:** kept pure-scan; atomic claim deferred to 3.1 RunRecord
  (see 1.7 above) because an in-resolver claim breaks within-submit idempotency.
