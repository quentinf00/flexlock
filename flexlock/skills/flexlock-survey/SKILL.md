---
name: flexlock-survey
description: Map the experiment state of a FlexLock project — what ran, what failed, what's newest per stage, and which runs are tagged. Use when asked to summarize, audit, or get oriented in a results tree.
---

# FlexLock survey

Goal: produce a fast, accurate picture of a FlexLock results tree using only the
machine-readable query commands. Never read `run.lock`/`results.json` by hand —
the JSON contracts below are the interface.

## Procedure

1. **Whole-tree shape.** Run the graph once and read node statuses:
   ```bash
   flexlock graph <results_root> --format json
   ```
   Count nodes by `status`. Note every `failed`/`interrupted`/`running` node and
   every lineage edge. `kind` distinguishes `run` / `sweep_master` / `sweep_task`
   / `external` (a lineage source outside the scanned tree).

2. **Recency.** List runs newest-first:
   ```bash
   flexlock ls <results_root> --format json
   ```
   Group by stage name (the run dir's basename) and keep the newest per stage.

3. **Detail the interesting nodes.** For the newest run per stage *and* every
   failed node:
   ```bash
   flexlock show <run_dir> --format json
   ```
   Read `status`, `note`, `target`, `error` (exc_type + traceback for failures),
   `results`, and `lineage.upstream`/`downstream`.

4. **Tags** (human-blessed checkpoints):
   ```bash
   flexlock tag -l
   ```

## Status meanings

| status | meaning |
|---|---|
| complete | `run.complete` present — cache hit, trustworthy |
| failed | `run.error` present (single) or a failed task (sweep) — see `error` |
| interrupted | bare `run.lock`, no completion — killed **or still running in-process** (no liveness probe) |
| running | sweep with pending/running tasks |
| pending | queued sweep task not yet claimed |
| unknown | nothing recognizable on disk |

Caveat: `interrupted` on a single run is ambiguous — it may be a live process.
Check timestamps / the scheduler before declaring a run dead.

## Suggested summary structure

- One-line health: `N complete, M failed, K running/interrupted`.
- Per-stage table: stage · newest status · timestamp · note · key metric.
- Failures section: each failed node with `exc_type` and a one-line cause.
- Tagged runs and their lineage.
- Recommended next actions (re-run, reclaim, gc).
