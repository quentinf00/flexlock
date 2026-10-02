# Changelog

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
