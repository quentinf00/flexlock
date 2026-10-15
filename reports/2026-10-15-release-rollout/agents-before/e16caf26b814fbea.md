

<!-- flexlock-release-compatibility -->
## FlexLock release compatibility (2026-10-13)

The installed environment uses FlexLock 0.9.2. This project manifest and
lockfile now pin the reviewed local 0.9.2 wheel, so Pixi keeps that release.
FlexLock dependency compatibility is checked; full environment synchronization
and scientific workload replay are separate checks. Before launching new work,
check the actual environment:

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


<!-- flexlock-project-workflow -->
## FlexLock project workflow (0.9.2; 2026-10-14)

Shared recipes: [workflow guidelines](/ontap/user/qfebvre/flexlock-execution-validation/docs/workflow_guidelines.md).
Release scope: [0.9.2](/ontap/user/qfebvre/flexlock-execution-validation/docs/release_0_9_2.md).
Project transition proposals: [review draft](/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-13-workflow-validation/TRANSITION.md).
The guidelines are maintained centrally; keep concrete project choices and exceptions here.
Research, knowledge and reporting instructions elsewhere in this file continue to apply.

- Use a fresh absolute run destination; track/arm/run is a useful naming convention,
  not a required schema or an automatic architecture selector.
- Select concrete upstream runs in configuration. Keep data snapshots tied to effective
  callable input arguments, and producer lineage tied to the corresponding selection.
  Preserve direct run_lock interpolation, overrides and sweep-file usage.
- Freeze file-list campaign membership. Check accepted outcomes for every expected item
  before aggregation; queue completion alone does not establish scientific coverage.
- Keep resource profiles separate from scientific choices. For different stage resources,
  use a small orchestration script with --after and persisted accepted job IDs. A reporting
  failure after submission must not cause blind resubmission.
- Retain original locks and artifacts. Before archiving config entrypoints, audit callers;
  before moving outputs, audit upstream references and active queue ownership.

Project starting point: Start with one Python config entrypoint and explicit retained-input bindings. Add separate stage or track modules only when actual reuse warrants them. Keep existing scientific parameters, split definitions and artifact paths during the first bounded comparison. Keep smoke/full/subset month sweep files and explicit selected-month membership; do not create one config per month.

This section guides new work; it does not assert that all historical workflows have
been replayed or that production configs/artifacts have been reorganized. Record actual
entrypoints, selected artifact paths and validation outcomes here when a project adopts
its first recipe; do not infer missing historical provenance.
<!-- /flexlock-project-workflow -->

<!-- flexlock-adoption-task -->
## Next priority: FLEXLOCK-ADOPT

The accepted highest-priority task for this checkout is in [TODO.md](/scale/user/qfebvre/projects/2508_nextgems/plans/TODO.md).
Follow [central handoff](/ontap/user/qfebvre/flexlock-execution-validation/docs/project_adoption_handoff.md) and report to
`/ontap/user/qfebvre/flexlock-execution-validation/reports/project-adoption/2508_nextgems--nextgems_tc/report.md` for review.
Verify actual installation before adoption; preserve scientific protocols and artifacts.
Other project instructions remain applicable. No expensive run or broad cleanup is
implicitly authorized by this task.
<!-- /flexlock-adoption-task -->

<!-- flexlock-project-adoption -->
## FlexLock adoption: preprocessing campaign (2026-10-14, submitted for central review)

Environment: nextgems_tc pixi env (`/scale/scratch/qfebvre/pixienvs/nextgems_tc-13266959035230603531/envs/default`),
FlexLock 0.9.2 from the pinned local wheel. On non-GPU nodes `pixi run` needs `CONDA_OVERRIDE_CUDA=12`.
Run everything from `nextgems_tc/` (queue `_target_` = `scripts.preprocess_full.preprocess.preprocess_chunk`).

**Only FlexLock caller:** the full-catalogue preprocessing (`scripts/preprocess_full/`). Adopted recipe —
frozen membership, one exported queue of complete configs, fresh absolute root, project coverage gate
before aggregation (`campaign.py`):

```sh
python -m scripts.preprocess_full.campaign export manifests/preproc-<smoke|full|repair>-v1.json /abs/ROOT /abs/ROOT.queue.yaml
PYTHONPATH=. flexlock-run --sweep-file /abs/ROOT.queue.yaml --sweep-root /abs/ROOT/queue \
    [--slurm-config configs/slurm_cpu_campaign.yaml --print-job-id]   # local without --slurm-config
python -m scripts.preprocess_full.campaign check     manifests/...json /abs/ROOT /abs/ROOT.coverage.json [--accept missing_zarr,...]
python -m scripts.preprocess_full.campaign aggregate manifests/...json /abs/ROOT /abs/ROOT.aggregate.json [--accept ...]
```

- Sweep definitions are the membership files in `manifests/` (smoke 4 storms / 2 chunks; full 9,834
  storms + 25 excluded-with-reason / 200 chunks, chunking identical to the legacy run; repair delta =
  the 38 legacy failed+unreadable storms / 4 chunks — not launched: needs the ocean-time guard first).
  Do not regenerate a membership in place (`freeze` writes with `x`); make a new versioned file.
- The recipe sets `reuse_existing=False`: an existing storm file in the campaign is a failure, not a
  cache hit. Per-storm problems (missing_zarr / unreadable / failed / too_short) are recorded per storm
  inside a successful chunk; the gate fails unless each such outcome is accepted by name with `--accept`.
- `aggregate` re-runs the gate and writes `ROOT/manifest_all.parquet` only if it passes.
- **Retained product (unchanged, in place):** `/scale/project/ifremer-isi-jumeaunumerique/quentin/nextgems_preproc/v1`
  (`storms/*.nc`, `manifest_all.parquet` sha256 in `reports/flexlock-adoption/legacy_sweep_coverage.json`,
  `flexlock/sweep/` 200/200 done). `campaign check-legacy manifests/preproc-full-v1.json OUT.json` re-validates
  it (0 issues on 2026-10-14). Its records have empty `_snapshot_`: no source/track/zarr identity exists for it.
  Downstream consumers (`scripts/lejepa/build_corpus.py`, `scripts/m1_gen|m2_baseline/build_dataset.py`) bind it
  by explicit path; they are plain scripts, not FlexLock stages.
- Legacy caller kept: `preprocess.py` with `membership=None` (defaults unchanged) and the historical
  `tasks.yaml` / `configs/slurm_cpu_worker.yaml`; `make_tasks.py` now refuses to overwrite `tasks.yaml`.
- Not FlexLock (deferred, see the central report): M0/M1/M2/LeJEPA training, evaluation and probe scripts,
  launched by `slurm/*.sbatch`. FlexLock writes `refs/flexlock/runs_*` snapshot refs into this git repo.

Evidence: `../reports/flexlock-adoption/README.md`. Central report:
`/ontap/user/qfebvre/flexlock-execution-validation/reports/project-adoption/2508_nextgems--nextgems_tc/report.md`.
<!-- /flexlock-project-adoption -->
