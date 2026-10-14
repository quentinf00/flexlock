# TODO

Accepted next work only. Promote an item from [IDEAS.md](IDEAS.md) after its
hypothesis, comparison, and success criterion are agreed. Durable findings
belong in [REVIEW.md](REVIEW.md).

## Active

### T1 — Replace Naga with FlexLock and make entry points reproducible

- **Priority:** blocking
- **Origin:** Naga no longer exists; migrate against the current
  [FlexLock usage guide](/scale/user/qfebvre/projects/2509_flexlock/flexlock/docs/usage_guide.md).

**Goal:** Every train/evaluate command has a stable, reproducible FlexLock run
record and no Naga dependency or runtime convention remains.

**Accepted scope:**

- add FlexLock as a package dependency and remove `NAGA_DEBUG`;
- replace `from naga import clicfg, runlock` and `mlflow_lock` in
  `train_gs.py` with `flexcli`/`py2cfg`, automatic target-repository tracking,
  `_snapshot_.data`, and `mlflow_context` where useful;
- convert `train_transformer.py` and `diagnose_transformer.py` from bespoke
  `argparse`, exception swallowing, notebook reloads, and `${now:}` paths to
  importable target functions with stable `save_dir` values and
  `save_dir_policy="timestamp"` or `"increment"` at submission time;
- model the workflow as stages under one `pipeline_dir`: fit splats, train
  dynamics, evaluate; link upstream runs with `_snapshot_.prevs` and read
  frozen upstream settings from `run.lock` rather than today's config;
- return JSON-serializable metrics so FlexLock writes useful `results.json`;
- add Pixi tasks for smoke runs and use an `if __name__ == "__main__":` guard
  for isolated/CUDA or sweep execution.

**Non-goals:** no model or loss changes in this task; do not mix migration with
scientific improvements.

**Validation:** `rg -n 'naga|NAGA_' src pyproject.toml` is empty; a CPU toy run
writes `run.lock`, `run.complete`, and `results.json`; a repeated `smart_run`
cache-hits; a failed run writes `run.error`; `dry_run=True` validates the Slurm
submission without launching it.

**Completion criterion:** the three stages can be reproduced from their saved
locks in a fresh process, and a downstream evaluation identifies the exact
splat and dynamics runs it consumed.

### T2 — Repair correctness defects in the Gaussian representation

- **Priority:** blocking
- **Engineering implementation completed:** 2026-08-18
- **Evidence:** `tests/test_gaussian_bank_gs.py` (6 focused tests) and the
  complete synthetic benchmark smoke test. Scientific validation on held-out
  EO fields remains part of T3.

**Goal:** Make the renderer and adaptive-density code mathematically consistent
before drawing conclusions from reconstruction loss.

**Accepted scope:**

- represent a 2-D rotation as an unconstrained angle; normalizing the current
  one-component tensor collapses it to approximately `-1` or `+1` radian;
- compare activated scales to `max_scale` (the current code compares a positive
  scale to `log(max_scale)`) and compare activated opacity to `min_opacity`
  (the current code compares it to a negative logit);
- repair the impossible densification interval: `densify_from=2000` and
  `densify_until=500` means the branch never runs in a 750-step default run;
- enforce `max_gaussians`, preserve optimizer state when resizing parameters,
  and guard empty masks/zero denominators/too many initialization samples;
- decide and test the renderer semantics: normalized radial-basis interpolation
  versus alpha compositing. The current normalization removes much of opacity's
  intended meaning;
- make configured learning rates and adaptive-control thresholds authoritative
  instead of hard-coded values.

**Validation:** analytic covariance/rotation tests, finite-gradient tests,
densify/clone/prune unit tests, a synthetic moving-vortex reconstruction, and a
CPU smoke train. Report parameter count and serialized byte count, not only
pixel loss.

**Completion criterion:** every adaptive-control branch is exercised by tests;
rendering is finite and differentiable; the documented parameter semantics
match saved checkpoints.

### T3 — Build a leakage-safe representation benchmark and go/no-go gate

- **Priority:** blocking scientific gate
- **Infrastructure status:** implemented 2026-08-18; synthetic smoke comparison
  passes. The actual held-out-storm comparison is pending an accessible dataset
  export and external ZFP/SZ/JPEG2000 baselines.

**Goal:** Establish whether splats are a useful representation of the fields,
independently of forecasting.

**Accepted scope:**

- split by storm identity and forecast initialization, never by random pairs;
- compute normalization from the training partition only and persist it in the
  run; use physically meaningful handling for signed `U,V` and missing values;
- compare Gaussian splats at several budgets against raw/downsampled grids,
  JPEG2000 or ZFP/SZ-style scientific compression, a low-rank/PCA baseline,
  and one compact convolutional or neural-field autoencoder;
- measure physical-space RMSE/MAE, vector-wind speed and direction error,
  spectral error, gradient/extreme-wind error, coastline behavior, encode time,
  decode time, peak memory, and actual bits per field;
- separately time per-scene fitting. Thousands of independent optimization
  loops are part of the cost, not preprocessing to hide from the comparison.

**Non-goals:** no transformer or diffusion scaling.

**Validation:** held-out storms and at least one held-out basin/model/source;
rate--distortion curves with uncertainty over storms; identical spatial support
and physical units for all methods.

**Go/no-go criterion:** continue to temporal splat modeling only if a splat
configuration is Pareto-competitive with simple baselines and provides a
specific secondary benefit (adaptive sparsity, localized editing, irregular
sampling, or fast region-of-interest decoding). Low reconstruction loss alone
is insufficient.

## Next, conditional on T1–T3

### T4 — Replace pair construction and correspondence with a valid temporal task

**Goal:** Define causal examples and targets whose identities are not artifacts
of independent per-frame fitting.

**Accepted scope:**

- sort lead times explicitly and assert positive `target_time-source_time`;
- use only operationally causal inputs and hold out complete storms/cycles;
- replace recursive fallback on missing checkpoint files with an indexed,
  validated manifest;
- test three correspondence choices: persistent/shared anchors, one-to-one
  optimal transport using position plus attributes, and correspondence-free
  rendered-field/set loss;
- distinguish transport/advection, birth/death, and attribute evolution rather
  than forcing every source primitive to a nearest target primitive.

**Baseline:** persistence/advection in grid space, a small grid CNN/neural
operator, and a linear splat-delta model.

**Completion criterion:** one-step and autoregressive skill beats persistence
on held-out storms without relying on pair leakage, and the conclusion is
stable across correspondence choices.

### T5 — Replace quadratic full attention and establish forecasting value

**Goal:** Test a scalable temporal architecture only after the representation
and correspondence gates pass.

**Accepted scope:** use permutation-equivariant local/radius graph attention,
hierarchical tokens, or fixed sparse neighborhoods; include absolute physical
coordinates, lead-time encoding with an explicit sign convention, masks, and
storm/environment conditioning; predict distributions or ensembles where the
future is not identifiable from a single field.

**Validation:** memory/time scaling in number of primitives; direct and
autoregressive forecasts; physical diagnostics including spectra, extrema,
radial wind, track-relative structure, and calibration.

**Completion criterion:** beat the strongest compute-matched grid baseline in
either forecast skill at equal cost or cost at equal skill on held-out storms.

## Promotion template

### T<number> — Title

- **Accepted:** YYYY-MM-DD
- **Origin:** idea or evidence

**Goal:**

**Accepted scope:**

**Baseline and comparison:**

**Non-goals:**

**Validation:**

**Completion criterion:**
