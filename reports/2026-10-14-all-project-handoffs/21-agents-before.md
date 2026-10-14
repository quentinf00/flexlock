# Agent Guidance: sample_project

## Project Structure
- `src/sample_project/`: Core implementation.
    - `cnf/`: Conditional Neural Field components.
    - `diffusion/`: Latent diffusion models.
    - `data/`: Preprocessing and data loading.
    - `evaluate/`: Reconstruction and assimilation scripts.
- `outputs/`: Training artifacts and results.
- `configs/`: Execution configurations.

## Project Objective

Reproduce the ConFiLD (see docs/confild.md when necessary) experiment on a NATL60 ssh (available here /scale/user/qfebvre/projects/251023_perceiver_da/2020a_SSH_mapping_NATL60/dc_ref):

see docs/project_steps.md
the original ConfilD implementation is here /scale/user/qfebvre/projects/260506_hafs/CoNFiLD

## Flexlock

You must use the flexlock library to configure/run/distribute/orchestrate  the different stages/experiments of the project

You are a beta tester, 
- you should refer first to the documentation: ../flexlock/docs and only inspect the code when you encounter an error
- Maintain a flexlock wiki  `flexlock_wiki/` with:
    - Use cases (should be framed as user stories): with best solution so far
    - Fail cases: failed command, misunderstood doc, unintuitive interface, code bug
    - Improvements:
        - doc updates
        - bug fixes
        - missing features
- Refer to the wiki to check if the intended usage already is in it with a adequate solution.

## Environment
The project uses pixi to manage dependencies
You have access to a slurm cluster, and to 2 gpus locally








## Key Constraints
- **CNF Architecture**: Currently supports both standard MLP and FiLM conditioning.
- **Diffusion**: Operates on latent vectors $z$ produced by the CNF stage, using temporal windowing to learn sequence structure.

## Verification
- No dedicated test suite is currently defined in `pyproject.toml`. Verification should be done via `run_*.py` scripts and inspecting `outputs/`.

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

Project starting point: Start with one Python config entrypoint and explicit retained-input bindings. Add separate stage or track modules only when actual reuse warrants them. Keep existing scientific parameters, split definitions and artifact paths during the first bounded comparison.

This section guides new work; it does not assert that all historical workflows have
been replayed or that production configs/artifacts have been reorganized. Record actual
entrypoints, selected artifact paths and validation outcomes here when a project adopts
its first recipe; do not infer missing historical provenance.
<!-- /flexlock-project-workflow -->
