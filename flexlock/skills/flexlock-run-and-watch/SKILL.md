---
name: flexlock-run-and-watch
description: Launch a FlexLock run or sweep, poll it to completion, and triage failures from run.error. Use when asked to run an experiment and report the outcome, or to babysit a sweep.
---

# Run and watch

## Launch — always record intent

Pass `--note` explaining *why* this run exists; it lands in `run.lock` and shows
up in `show`/`graph`/`report` without affecting caching:

```bash
flexlock-run -d myproject.pipeline.cfg -s train --note "baseline before lr sweep"
```

Sweeps add `--sweep`/`--sweep-file`/`--sweep-key` and `--n_jobs`; HPC adds
`--slurm-config`/`--pbs-config`.

## Poll (background, 30–60 s cadence)

- **Single run:** poll the status field.
  ```bash
  flexlock show <run_dir> --format json      # read .status
  ```
  `complete` → done; `failed` → triage; `interrupted` → may still be running,
  re-check after a bit before declaring it dead.

- **Sweep:** watch the task DB, then summarize via the master.
  ```bash
  flexlock-status <sweep_root>/run.lock.tasks.db
  flexlock show <sweep_root> --format json   # aggregate .tasks counts
  ```

## Triage a failure

Read the per-dir sidecar (no sqlite needed):

```bash
flexlock show <run_dir> --format json        # .error = {exc_type, exc_message, traceback}
```

Classify by `exc_type`:
- **User-code error** (`ValueError`, `KeyError`, shape mismatch, assertion): fix
  the code/config, then re-run.
- **Node/infra fault** (CUDA `cudaErrorSystemNotReady`, OOM, `interrupted` with
  "orphaned"): not your code — retry elsewhere.

## Recovery table

| situation | action |
|---|---|
| sweep tasks stranded `running` by a dead worker | `flexlock-worker --task-db <db> --reclaim` |
| want to force re-execution of a cached run | re-run with `force=True` / `--force` (clears `run.complete`; success clears `run.error`) |
| clean up interrupted attempts | `flexlock gc --incomplete` |

**Never delete run directories by hand** — use `flexlock gc` so tagged runs and
their lineage stay protected.
