# Implementation plan: simplify config resolution / interpolation

Goal: replace the "three binding times hidden in one `${...}` syntax" design with
explicit, single-purpose mechanisms, so the InterpolationKeyError bug class and
the freeze.py grammar parser largely disappear.

Target semantics after this plan:

| Binding time      | Mechanism                                         | Replaces                                  |
|-------------------|---------------------------------------------------|-------------------------------------------|
| submit-time       | eager OmegaConf resolution (everything by default) | freeze.py simple-ref chain following       |
| save_dir creation | `save_dir_policy=` flag on runner/submit           | `${vinc:}`, `${now:}` in configs           |
| stage-start       | deferred resolvers: `run_lock` (and `latest`)      | same resolvers, but ONE resolution point   |
| per-sweep-item    | merge override BEFORE resolution                   | `${.variable}` placeholder tricks          |

---

## Phase 1 — `save_dir_policy` on the runner (kills `${vinc:}`/`${now:}` in configs)

**New API**

```python
proj.submit(cfg, save_dir_policy=None | "increment" | "timestamp")
# CLI: flexlock run ... --save-dir-policy increment
```

**Implementation**

1. New module `flexlock/save_dir.py`:
   - `next_versioned_path(path, fmt="_{i:04d}") -> str` — move the body of
     `vinc_resolver` (resolvers.py:61) here as a plain function; the resolver
     becomes a thin deprecated wrapper around it.
   - `apply_save_dir_policy(cfg, policy) -> None` — resolves `cfg.save_dir`
     to a concrete string exactly once:
     - `"increment"`: `next_versioned_path(base)`, then **claim atomically**
       with `mkdir(exist_ok=False)` + retry on collision. This fixes the
       documented vinc race (resolvers.py:73-77) at the right layer.
     - `"timestamp"`: `base / now.strftime(config.TIMESTAMP_FORMAT)`.
     - `None`: resolve as-is (current behaviour).
2. Call sites:
   - `api.py:577-590` — replace the "resolve save_dir exactly once" try/except
     with `apply_save_dir_policy(config, save_dir_policy)`.
   - `runner.py` `_prepare_node` (runner.py:365) and `_build_node_cfg`
     (runner.py:298) — thread the CLI flag through; keep the timestamp
     fallback but route it through the same function.
3. Sweep interaction: the policy applies once to the sweep root; items keep
   getting `sweep_root/sweep_{i:04d}` via the existing `dir_suffix` path
   (api.py:1144-1150). Assert policy is not applied per-item.
4. Deprecation: `vinc_resolver`/`now_resolver` emit a `DeprecationWarning`
   pointing at `save_dir_policy` when fired. Keep them registered and working
   for one minor version.

**Deletions unlocked (end of phase or Phase 5)**

- The vinc cache-draining hack `api.py:758-773` (re-wrap after
  `to_container(resolve=True)`).
- The `${vinc:}` special-casing comment/path in `snapshot.py:99`.
- The `load_sweep` quoting hack (utils.py:414) that string-protects resolver
  calls so vinc fires late.

**Tests**

- `apply_save_dir_policy` unit tests: increment idempotency within one submit,
  atomic-claim collision retry, timestamp format.
- Regression: two concurrent submits with `"increment"` on the same base get
  distinct dirs (the race vinc could not fix).
- Existing vinc tests stay green (deprecated path still works).

---

## Phase 2 — one deferred-resolution point + rebuild freeze.py on OmegaConf

**2a. Deferred stub context manager**

New helper in `resolvers.py`:

```python
@contextmanager
def deferred_stubbed():
    """Re-register run_lock/latest so they re-emit their own call string
    with args already resolved by OmegaConf."""
    # run_lock stub: lambda *args: "${run_lock:" + ",".join(map(str, args)) + "}"
```

Key fact this exploits: OmegaConf resolves nested interpolations in resolver
args *before* invoking the resolver. So resolving
`${run_lock:${precompute_dir},key}` under the stub yields the frozen string
`${run_lock:/data/precomputed,key}` — with zero string parsing on our side.
(Today's `_resolve_in_root` bug would have been structurally impossible.)

Verify this arg-pre-resolution behaviour against the pinned omegaconf version
in a dedicated test before building on it.

**2b. Reimplement `select_and_freeze_root_refs`**

New implementation (same signature, freeze.py):

1. Deep-copy the root config; enter `deferred_stubbed()`.
2. `OmegaConf.resolve(root_copy)` — OmegaConf itself does all simple-ref,
   cross-tree, multi-hop, mixed-string, and relative-ref resolution, with
   correct grammar, while deferred calls collapse to frozen call strings.
3. `OmegaConf.select(root_copy, key)` and return a detached copy.
4. Error mapping: catch `InterpolationKeyError`/`InterpolationResolutionError`
   and re-raise as `UnresolvedInterpolationError` with the existing
   "set it via overrides=..." hint (freeze.py:240-244).

Delete: `_freeze_walk`, `_resolve_in_root`, `_freeze_embedded_in_root`,
`_process_interps_in_string`, `_process_one_interp`, `_freeze_simple_ref`,
and the balanced-brace scanner — the whole hand-rolled grammar.

Known behaviour changes to handle explicitly:

- **Relative refs `${.foo}`**: OmegaConf resolves them (correctly, since the
  tree is still attached). Today they are preserved verbatim. The only
  consumer of "preserve verbatim" is the sweep `${.variable}` placeholder —
  removed in Phase 3, so land 2b together with or after Phase 3. Any other
  intra-stage relative ref resolves to the same value either way.
- **Type preservation**: stub output is a string; real `run_lock` returns
  native types at stage start, unchanged.
- **Missing keys inside deferred args** resolve-fail early now (good —
  surface at submit, not on the worker).

**2c. Single deferred-resolution point**

New function `resolve_deferred(cfg) -> DictConfig` (freeze.py or resolvers.py):
`to_container(resolve=True)` with real resolvers + re-wrap. Called at exactly
two places:

- `worker.py:worker_loop` right after `merge_task_into_cfg` (worker.py:122).
- api.py local single-run path, replacing the existing eager
  `to_container(resolve=True)` at api.py:770.

Document: "`run_lock`/`latest` fire once, at stage start, on the worker."

**Tests**

- Port `tests/test_node_selection.py` — assertions on frozen output stay
  identical (they describe the same contract); delete tests that pin
  internals of the old scanner.
- Keep all regression tests (cross-tree resolver args, multi-hop mixed
  strings, `${latest:}` preservation, etc.) as black-box contract tests.

---

## Phase 3 — sweeps: merge before resolution, serialize plain dicts

1. `_submit_sweep` (api.py:1137-1151): for each override, merge into the
   **base config first**, then run the Phase-2 freeze (eager resolve +
   deferred preserved) on the merged item. Item-injected keys (e.g.
   `variable`) exist before any resolution, so `${.variable}`-style
   placeholders and their `InterpolationKeyError`s disappear.
2. `_validate_sweep_save_dirs`: operate only on merged, resolved items —
   never touch `base_config.save_dir` (the exact bug in
   `test_submit_sweep_relative_save_dir_ref`). The unresolved-base guard
   becomes dead code; remove it.
3. Task DB payloads: store `to_container(resolve=False)` of the merged item —
   now a plain dict of concrete values plus deferred call strings. Worker
   side: `merge_task_into_cfg` keeps working unchanged; `resolve_deferred`
   (Phase 2c) completes the config.
4. `print_config` sweep preview (api.py:596-602) uses the same merged items,
   so preview == execution.

**Tests**

- Existing sweep regression tests must pass unchanged (they test observable
  behaviour).
- New: sweep item referencing an injected key via a *normal* ref
  (`${variable}`) — the pattern that replaces `${.variable}`; document the
  migration in the changelog.

---

## Phase 4 — preflight check (side-effect-free full resolution)

- `Project.check(config=None, sweep=None, ...)` + `flexlock run --check`:
  run the full Phase-2/3 pipeline under `deferred_stubbed()`, including
  per-sweep-item merges, and report every resolution error with its
  `full_key` — without touching the filesystem (possible because vinc's
  `mkdir` side effect is gone from resolution).
- Wire `print_config=True` through the same code path so preview can never
  diverge from submit.

---

## Phase 5 — deprecation & cleanup

- Remove (after one deprecation minor):
  - `${vinc:}` / `${now:}` resolvers (keep `next_versioned_path` helper).
  - api.py:577-590 resolve-once block, api.py:758-773 cache-drain block.
  - snapshot.py vinc special case; utils.py `load_sweep` quoting hack.
- Docs: rewrite the interpolation section around the binding-times table at
  the top of this file; add a migration guide
  (`${vinc:...}` → `save_dir_policy="increment"`, `${.variable}` → `${variable}`).

---

## Sequencing & effort

| Phase | Depends on | Risk | Est. |
|-------|-----------|------|------|
| 1     | —         | low  | 0.5–1 day |
| 2a    | —         | low (one omegaconf-behaviour test gates it) | 0.5 day |
| 2b    | 2a, 3 (relative-ref removal) | medium | 1–2 days |
| 2c    | 2a        | low  | 0.5 day |
| 3     | —         | medium | 1 day |
| 4     | 2, 3      | low  | 0.5 day |
| 5     | all       | low  | 0.5 day |

Recommended landing order: **1 → 2a → 2c → 3 → 2b → 4 → 5**. Each step keeps
the full suite green; 2b (the freeze.py rewrite) goes last among the
functional phases because it needs the sweep-placeholder pattern gone first.

## Risks / open questions

1. **OmegaConf arg pre-resolution** (2a's foundation): verified by a pinned
   test; if a future omegaconf changes this, the test fails loudly.
2. **Fingerprint stability**: configs frozen by the new path may differ
   textually from the old path (e.g. relative refs now resolved), changing
   `smart_run` fingerprints once → one-time cache miss for existing runs.
   Call this out in the changelog.
3. **`${latest:}`**: kept as a deferred read-only resolver alongside
   `run_lock`. If it turns out unused in practice, fold it into Phase 5
   removals instead.
4. **Backward compat window**: old configs with `${vinc:}` keep working
   until Phase 5; CI should run the example projects under both styles
   during the window.
