# 0.10.0

- Retire automatic cross-run cache search, marker-based partial-stage resume and
  chained fanout; retain explicit producer selection, named sweeps and ordered stages.
- Record invocation source scopes separately from shared source capture.
- Preserve authoritative result records, pre-submission ownership guards, scheduler
  dependencies and matching-worker queue continuation.
- Publish portable workflow recipes and align shipped agent skills with explicit
  producer selection and fresh-attempt recovery.

# Changelog

## 0.10.0rc1 (local candidate, 2026-10-16)

- Remove automatic cross-run cache search, submission cache keywords and CLI
  `--check-exists`, `Project.exists/get_result`, and chained fanout APIs.
- Reject old marker-based stage-resume payloads and worker-time unpinned run
  selectors under scheduler dependencies. Keep explicit future producer bindings.
- Preserve exact-path reuse, authoritative output validation, recorded queue
  continuation, ordered stages and provenance comparison. Tighten queue ownership
  checks so foreign queues and changed payloads cannot bypass destination guards.
- Include the unreleased source-attribution and project-feedback fixes described
  in [candidate migration notes](release_0_10.md).

This is an isolated validation candidate; no project environment upgrade or
scientific rerun is implied.

## 0.9.0 (2026-10-02)

### Added
- Composite pipelines across sweeps, local/HPC workers, and enqueue/dequeue.
- Full per-stage run records in directories or the task DB, including upstream
  references, code provenance, and code-drift detection.
- Environment lockfiles in run fingerprints.
- Preset tracking and `flexlock runs` / `flexlock presets`.
- `${run:...}` references to completed preset runs and `key=@name` config swaps.

### Fixed
- Composite task snapshots retain every executed stage instead of overwriting
  earlier stage records. Exports include each stage's inherited code and environment.

### Release infrastructure
- CI on Python 3.11–3.13, wheel/sdist checks, tag-driven PyPI and conda publishing,
  and GitHub Pages documentation.

The unreleased 0.8.3 fixes below are included in this release.

## 0.8.3 (unreleased)

### Fixed
- **Single HPC / `isolated=True` runs now get a full `run.lock`.** They used to
  keep the submit-time placeholder (`config` = `save_dir` + `_snapshot_` only)
  because the worker stored the real snapshot only in `run.lock.tasks.db`. That
  broke `${run_lock:...}` (`KeyError`), made `flexlock-run -c run.lock` a
  silent no-op, showed empty configs in `show`/`diff`/`ls`, linked no commits
  on `tag`, and let `gc` delete the upstreams of a tagged run. The worker now
  writes the full snapshot (config, fingerprint, git state, `note`) atomically
  when its task owns the master dir. Sweep roots keep their placeholder.
- Readers (`${run_lock:...}`, `show`/`graph`/`why`/`report`, `flexlock-diff`,
  `ls`/`gc`/`tag`, `load_stage`, lineage, `flexlock-run -c run.lock`) fall back
  to the task-DB snapshot for placeholder `run.lock`s written by older versions.
- The worker refreshes `run.lock.tasks` when its queue drains, so it is no
  longer left at `[]` after a `wait=False` submit.
- `force=True` on a single HPC / isolated submission deleted `run.complete` but
  ran nothing: the old `done` row in the task DB was kept by `INSERT OR IGNORE`.
  The task DB is now reset and the task re-executes. The reset also drops the
  cached sqlite connection, which kept writing to the deleted DB file.
- Slurm backend: forkserver compatibility fix.
- `docs/hpc_integration.md`: the task DB lives inside `save_dir`, not in its
  parent. The overview section, clobbered by an earlier edit, is restored.

### Added
- `flexlock.run_record.load_lock_data(run_dir)`: side-effect-free effective
  `run.lock` (placeholder → task-DB snapshot).
- `flexlock.run_record.materialize_lock(run_dir)`: one-off rewrite of a
  placeholder `run.lock` (keeps `run.lock.placeholder.bak`).
- `flexlock repair-locks <root> [-n]`: runs `materialize_lock` over a results tree.
- `flexlock.taskdb.reset_db(db_path)`.
