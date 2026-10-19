---
name: flexlock-run-and-watch
description: Launch a FlexLock run or sweep, poll it to completion, and triage failures from run.error. Use when asked to run an experiment and report the outcome, or to babysit a sweep.
---

# Run and watch

## Launch — always record intent

Pass `--note` explaining *why* this run exists; it lands in `run.lock` and shows
up in `show`/`graph`/`report` without changing computation identity:

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

Inspect the failure and retained products before choosing recovery. Code/config/data
changes get a fresh attempt destination; bind retained producers explicitly and
select only remaining stages. Infrastructure failure is not permission to retry
while an old worker may still be active.

## Recovery

- Continue an unchanged queue with its matching worker/environment; keep failed
  rows visible. Reclaim a stranded plain item only after its old worker stopped.
  Do not blindly replay partially completed composites.
- `--save-dir-policy skip` validates a completed selected record and its recorded
  outputs; `CACHED` does not claim equivalence to current code/config.
- `--force` deliberately replaces inactive provenance in place. Prefer fresh
  destinations when retaining evidence. Force never bypasses active queue ownership.
- Persist accepted scheduler IDs. If reporting fails after acceptance, inspect
  scheduler state before retrying submission. Submission is not completion.
- Inspect all expected items and required products before aggregation.

`flexlock gc -n` previews local run cleanup. `--refs` is not a cross-project
retention audit; `--incomplete` bypasses normal tag protection. Do not prune
evidence or snapshot refs without checking retained consumers and active owners.
