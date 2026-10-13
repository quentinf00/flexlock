

<!-- flexlock-release-compatibility -->
## FlexLock release compatibility (2026-10-12)

The installed-environment migration pilot uses FlexLock 0.9.2. Project
manifests and lockfiles are not yet repinned: a Pixi synchronization can restore
an older installation. Before launching new work, check the actual environment:

```sh
python -c "import flexlock; print(flexlock.__version__, flexlock.__file__)"
```

Use the following execution contracts when working with the updated release:

- Destination ownership/collision checks run before scheduler submission.
  Use a fresh destination by default. Explicit `--force` may overwrite inactive
  prior provenance; it cannot bypass pending/running queue ownership. Inspect
  and continue an existing queue instead of resubmitting over it.
- Existing `${run_lock:...}` producers bind at submission; changing or removing
  their records before consumer execution causes failure. Choose concrete
  upstream paths. Promised inputs with `--after` retain that exact path and bind
  when available; a newer run is not an automatic replacement.
- Invalid declared outputs or missing authoritative records prevent successful
  reuse. Worker/queue failure must be checked; a scheduler submission ID is not
  evidence of successful computation or complete cohort coverage.
- Queue layout 2 omits `.flexlock-queue.json` for fresh nested products. Use
  FlexLock's `load_record` and shared queue readers rather than reading that
  pointer directly. All consumers of new queues need FlexLock 0.9.1+.
  Keep pending products with their ancestor queue; preserve referenced records
  when exporting or moving provenance. Existing/external pointers remain.
- Python configuration, `py2cfg`, `@` presets, direct upstream overrides and
  sweeps remain supported. Automatic cache discovery has not yet been retired;
  this pilot does not establish scientific equivalence or project acceptance.

FlexLock 0.9.2 removes its unused pandas dependency. It neither installs nor
downgrades pandas. Optional MLflow and scientific packages retain their own
dependency requirements. Library ownership checks passed for the migrated
installations; scientific workloads have not been replayed by this pilot.

This section documents FlexLock compatibility only. Existing project research,
knowledge and reporting instructions continue to apply.
<!-- /flexlock-release-compatibility -->
