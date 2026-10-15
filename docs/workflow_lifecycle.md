# Processing, experiments and inference: connected recipes

Review draft, 2026-10-15, grounded in SAR's existing entrypoints. Preprocessing is
validated on small NetCDF fixtures; the collocation/release/L2 recipes below are
project implementation tasks, not claims of completed adoption. See SAR's
FLEXLOCK-LIFECYCLE task and central handoff.

Use names appropriate to the activity; track/arm/run is optional:

```text
datasets/features/<recipe>/<execution>/
datasets/collocations/<protocol>/<execution>/
experiments/<track>/<arm>/<run>/
releases/sarwave/<release>/<build-execution>/
processing/l2-wave/<release>/<campaign>/<execution>/
```

These are suggested new destinations, not instructions to move retained artifacts.

## Reusable processing products

SAR's preprocessing config freezes SAFE membership, extracts per-item features
and checks coverage inside each train/val/test assembly. Retain these producers
independently: multiple experiments can select the same preparation without copying
its files or recreating provenance. Use concrete root bindings, effective input
snapshots and existing run_lock overrides/sweeps.

Collocations are another shared branch: observations plus selected SAR inputs
produce evaluation data. The collocation/fast-validation split already permits
reuse across models. Before adoption, freeze protocol/membership and required
sources; missing sources or default feature fallbacks must not quietly certify
complete evaluation. A changed protocol creates a new comparison baseline.

## Experiments and selected model products

An experiment selects concrete preparation, collocation and checkpoint producers.
The workflow decides whether retained preparation remains scientifically suitable;
FlexLock records the choices and checks mechanical identity. Resource profiles
remain separate from scientific variants. Separate CPU/GPU allocations use ordinary
submissions, --after and persisted accepted-ID ledgers.

## Portable model release

SAR has ONNX export and a separate sarwaveifrproc processor. A project release-building
stage can select exact export/evaluation records and assemble a fresh self-contained
directory. A plain manifest describes model/config hashes, feature order, outputs
and units, supported input versions, inference/sampling settings, code/environment
identity and original provenance references. Include external normalization/assets
where they are not embedded. This is not a new FlexLock artifact class.

After relocation, runtime assets resolve inside the package. Original absolute
research paths remain provenance references, not runtime dependencies. Compare
research/exported predictions on bounded inputs with declared tolerances and
controlled randomness. Check actual signatures/dimensions; a product ID alone
is not a complete specification. A successful build is not publication or deployment.

## Batch inference and operations

Select a release and frozen SAFE membership, execute the existing processor through
a small recorded wrapper, and validate per-item product coverage before aggregation.
Keep processor interfaces where suitable. Define existing-output reuse, unsupported
versions and partial-product policies explicitly; job success alone is insufficient.

FlexLock can record packaging, evaluation and batch campaigns. An online service
can consume the release without FlexLock per request. Deployment, monitoring,
publication and rollback remain operational workflow decisions. No deployment or
expensive SAR campaign is authorized by these examples.
