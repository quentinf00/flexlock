# TODO

Accepted implementation scope only. Promote an item from
[IDEAS.md](IDEAS.md) after its experiment, constraints, baseline, compute
budget, and acceptance criterion have been agreed. Record the decision in
[DONE.md](DONE.md).

The OI post-processing baseline is now active. Other candidate promotion gates
remain documented in `IDEAS.md` and are not implementation authorization.

**Job submission requirement (user, 2026-09-21):** submit jobs through
FlexLock using its Slurm backend (`--slurm-config`), so scheduler tasks and
artifacts are traceable. A manually submitted sbatch wrapper around
`flexlock-run` does not satisfy this preference. Use an explicit fresh
`main.save_dir` before config resolution; the observed HPC increment policy
changed the root directory without updating nested logger/checkpoint paths.

### T20 — Observation reinjection (promotes I19)

- **Accepted:** 2026-10-04, user request.
- **Status (2026-10-04):** P0 pre-check done on CPU. Training arms A0–A2 are
  not implemented yet. Queue them after the T18 wide run (ETA ~Oct 7).
  **2026-10-07:** A0 and A1 queued (`configs/t20_reinjection.py`). Both
  finetune arm B `best.ckpt` (epoch 194; all 208 tensors transfer) with a
  fresh optimizer: lr 1e-4, 50 fixed epochs, no early stopping, seed 42,
  `shuffle_buffer=256`, `numactl --interleave=all`. A0 **676358** →
  inference **678985**; A1 **677696** → inference **681171**; joint drifter
  gate (A0, A1, arm B) **682844** → `results_starter_glob/t20_evaluation_2021`.
  A2 (cascade) still needs implementation.
  **2026-10-08/09:** both arms trained 50 epochs (~7 h 55 min each; 208/208
  tensors loaded). Validation:

  | run | best val_mse (ep) | mean ep 40–49 | IR / MW consistency RMSE K |
  | --- | ---: | ---: | ---: |
  | arm B | 0.4557 (194) | — | 0.410 / 0.439 |
  | A0 | 0.4502 (47) | 0.4518 | 0.403 / 0.434 |
  | A1 | 0.4547 (43) | 0.4574 | 0.397 / 0.406 |

  Interpretation:
  - A0 gains 1.2% on validation from 50 more epochs at lr 1e-4, which fits
    the underfitting reading.
  - A1 trades +1.0% on hidden pixels for a tighter fit to visible
    observations (IR −1.5%, MW −6%). IR consistency stays far above the
    ~0.26 K noise floor.
  - The joint drifter gate 682844 decides.

  **Gate result (2026-10-09; 678985/681171 → 682844, all exit 0; 483,320
  common matchups; `results_starter_glob/t20_evaluation_2021`). A1 PASSES.**

  | band (0–30/30–60/≥60) | arm B | A0 | A1 | A1 − A0 mK [95% CI] | ODYSSEA |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | global | 0.4654 | 0.4619 | **0.4552** | −6.7 [−7.3, −6.2] | 0.4760 |
  | equatorial | 0.3783 | 0.3771 | 0.3724 | −4.7 [−5.1, −4.3] | 0.3630 |
  | midlatitude | 0.4965 | 0.4915 | 0.4825 | −8.9 [−9.7, −8.2] | 0.5166 |
  | high latitude | 0.5890 | 0.5863 | 0.5838 | −2.5 [−5.3, −0.0] | 0.6209 |

  - A0 − arm B: −3.5 mK [−3.9, −3.1]. The extra 50 epochs at lr 1e-4 help on
    their own, so A0 is the right control.
  - Split by same-day IR (`t20_evaluation_2021/drifter_ir_split.csv`): A1 − A0
    is −5.7 mK on IR-observed pixels and −8.1 mK in IR gaps. The deficit to
    ODYSSEA on IR-observed pixels falls from +18.8 mK (arm B) to +10.0 mK.
    High-latitude IR-observed pixels are unchanged (+0.4 mK).
  - Observation fit (`results_starter_glob/t20_obs_fit`, 24 dates): global ±60°
    fit to IR is 0.321 (B), 0.318 (A0) and 0.308 K (A1), against ODYSSEA 0.252
    and the 0.256 noise floor.
  - Coherence at 50–100 km rises (Gulf Stream 0.29 → 0.33, Southern Ocean
    0.19 → 0.25) but stays below ODYSSEA (0.64–0.68). 25–50 km is still ≈ 0.
  - Acceptance met: global CI excludes 0 and no band regresses. Validation
    loss ranked A1 below A0 (0.4547 vs 0.4502), the opposite of the drifter
    gate, so val_mse on synthetic-cloud pixels is not a reliable proxy for
    this change.

  **A2 queued (2026-10-09).** `CascadeUNet`
  (`sst_ml_mapping/starter/model/cascade.py`):
  - a frozen arm B gives the first guess;
  - the refiner is initialised from arm B, with 10 extra zero-initialised
    channels (first guess ×5, visible-IR misfit ×5);
  - step 0 reproduces arm B exactly (CPU test, max difference 0.0);
  - same budget as A0/A1, `consistency_loss_weight` 0.1.

  Jobs: training **799592** → inference **799630** → four-arm gate **799684**
  (`t20_a2_evaluation_2021`; A0, A1, A2 and arm B on one common support).
  A2 is compared with A0 (same loss); A1's weight is not combined yet.

  **Slurm crash audit (2026-10-10): no requeue needed.** Accounting confirms
  all three A2 jobs `COMPLETED`, exit `0:0`:
  - **799592** training finished Oct 9 at 22:08:23 (9 h 52 min);
    `results_starter_glob/t20_a2_cascade/` contains `best.ckpt` and
    `epoch=49-step=3200.ckpt`; the log confirms all 50 epochs finished.
  - **799630** inference finished Oct 10 at 05:06:17 (6 h 58 min);
    `/scale/project/lops-siam-sst-ml/inference/t20_a2_2021_km_native/`
    contains all 365 nonempty daily NetCDF files for 2021, with no missing dates.
  - **799684** four-arm evaluation finished Oct 10 at 05:15:42 (9 min 25 s);
    `results_starter_glob/t20_a2_evaluation_2021/` contains drifter matchups
    and summaries, scale diagnostics, and ODYSSEA diagnostics.

  Each run has `run.complete`; its `run.lock.tasks.db` records the matching
  job ID, status `done`, no error, resolved configuration, and a parent link
  to its `run.lock`. Parent receipts record repository commit and dirty-tree
  identities and the `pixi.lock` hash. Recorded Git trees are available and
  include the untracked cascade/config code and environment lockfile.
  Earlier A0/A1 training/inference/gate IDs listed above also remain
  `COMPLETED`, exit `0:0`. No experiment jobs remain in the live queue.
  This audit verifies execution and artifact presence; A2 scientific
  acceptance still needs review of the completed gate outputs.

  **A2 gate summary inspection (2026-10-10):** existing
  `t20_a2_evaluation_2021/drifters/drifter_summary_common.csv` reports
  483,320 common matchups per product. RMSE (K):

  | band | arm B | A0 | A1 | A2 | ODYSSEA |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | global | 0.4654 | 0.4619 | 0.4552 | 0.4549 | 0.4760 |
  | equatorial | 0.3783 | 0.3771 | 0.3724 | 0.3714 | 0.3630 |
  | midlatitude | 0.4965 | 0.4915 | 0.4825 | 0.4812 | 0.5166 |
  | high latitude | 0.5890 | 0.5863 | 0.5838 | 0.5902 | 0.6209 |

  A2 improves global RMSE by 7.0 mK against A0, but is only 0.25 mK
  better than A1. High-latitude RMSE worsens by 3.9 mK (0.67%) against A0,
  within the 2% band tolerance, and by 6.4 mK against A1. A2 global bias
  is -0.0010 K (A1 -0.0195 K); MAE is 0.2876 K (A1 0.2924 K).
  On product-support observed/gap-filled strata, A2 RMSE is
  0.4274/0.5571 K versus A1 0.4289/0.5531 K. These support strata are
  not the requested same-day IR split. The gate did not write paired
  day-block confidence intervals, so formal A2 acceptance and superiority
  over A1 remain undecided; the tiny global difference does not justify A3.

  **Fine-scale energy (2026-10-10):** local FlexLock summary
  `pixi run --frozen flexlock-run -d configs.t20_spectral_summary:main`
  → `results_starter_glob/t20_a2_spectral_summary_20261010/`.
  Receipt and completion verified; recorded dirty Git tree contains the
  summary code/config and `pixi.lock`. Input spectra SHA-256 is recorded in
  `methodology.json`. Segment-weighted monthly PSDs integrated in frequency
  on common model/ODYSSEA segments give:

  | region | A2/A0 energy, 50–100 km | A2/A1 energy, 50–100 km | A2/ODYSSEA energy, 50–100 km | A2/ODYSSEA energy, 25–50 km |
  | --- | ---: | ---: | ---: | ---: |
  | Gulf Stream | 1.91 | 1.64 | 0.470 | 0.041 |
  | Kuroshio | 1.97 | 1.58 | 0.428 | 0.050 |
  | Southern Ocean | 1.37 | 1.18 | 0.195 | 0.018 |
  | Equatorial Pacific | 1.46 | 1.44 | 0.247 | 0.045 |

  A2 restores substantial SST variance at 50–100 km, especially in western
  boundary currents, but remains well below ODYSSEA. At 25–50 km its energy
  remains only 2–5% of ODYSSEA despite relative gains in three regions.
  These are SST-variance diagnostics on 12 regional monthly dates, not
  kinetic energy or proof of phase-correct fine structures. The existing
  gate spectra do not include coherence; A2 coherence remains unmeasured.

  **Interpretation (user, 2026-10-10): encouraging.** The cascade nearly
  doubles 50–100 km energy versus A0 in the Gulf Stream and Kuroshio,
  while improving global drifter RMSE versus A0 and matching A1 globally.
  This is promising progress toward recovering finer SST structure, even
  though 25–50 km energy remains strongly suppressed. Assess A2 coherence
  with same-day IR and the paired drifter confidence intervals before
  deciding whether A2 beats A1 or meets the condition for A3. No A3 launch
  is authorized by this interpretation.

  **Follow-up accepted (2026-10-10, user "Ok go"):** finish the A2
  paired day-block CIs, same-day IR-observed/gap drifter split, and P0a
  observation fit/coherence on the same 24 dates. Then test
  **A2 + consistency 1.0**, named `t20_a2_consistency1`: fresh arm B
  initialization, frozen first guess, same seed 42, lr 1e-4, 50 fixed
  epochs, shuffle buffer 256, model/data and optimizer policy as A2.
  Only consistency weight changes from 0.1 to 1.0 (IR and MW, as in A1).
  Existing A2 scientific source and `pixi.lock` were checked byte-for-byte
  against its recorded tree before adding diagnostic code: no differences.

  Config: `sst_ml_zarrpatch/configs/t20_followup.py`; resource profiles:
  `slurm_t20_a2_diagnostics.yaml`, `slurm_t20_a2_consistency1.yaml`,
  `slurm_t20_a2_consistency1_inference.yaml`,
  `slurm_t20_a2_consistency1_evaluation.yaml`. Training allocation matches
  A2: one A100, 256 GiB, 8 CPUs; expected ~10 h training plus ~7 h
  full-year inference. CPU diagnostics/evaluation use 64 GiB and 4 CPUs.
  All scheduler submissions use the FlexLock backend. Fresh output paths:
  - `sst_ml_zarrpatch/results_starter_glob/t20_a2_paired_ci_20261010/`
    (cheap local FlexLock analysis of existing matchups);
  - `sst_ml_zarrpatch/results_starter_glob/t20_a2_diagnostics_20261010/`;
  - `sst_ml_zarrpatch/results_starter_glob/t20_a2_consistency1/`;
  - `/scale/project/lops-siam-sst-ml/inference/t20_a2_consistency1_2021_km_native/`;
  - `sst_ml_zarrpatch/results_starter_glob/t20_a2_consistency1_evaluation_2021/`.

  Compare all five ML arms plus ODYSSEA on common drifter support;
  report paired 95% day-block CIs (2,000 resamples, seed 42), official
  0–30/30–60/≥60° bands, IR-observed/gap split, IR fit/noise reference,
  and coherence/gain at 25–50/50–100 km. Apply the existing 2% latitude
  regression guard; distinguish statistical RMSE superiority from spectral
  gains. One training seed remains a limitation. Assess the results before
  deciding on A3; this follow-up does not launch unrolling.

  **Follow-up results / runtime investigation (2026-10-11):** paired
  bootstrap completed in `t20_a2_paired_ci_20261010`; diagnostics job
  **1003680** completed in `t20_a2_diagnostics_20261010` with a FlexLock
  completion receipt. On 483,320 common drifter matchups, A2 minus A1
  global RMSE is -0.254 mK (95% paired day-block CI [-1.402, +0.854]):
  overall superiority remains inconclusive. Against A0 the difference is
  -6.984 mK [-7.920, -6.072]. Against A1, same-day IR-observed matchups
  improve by -5.027 mK [-6.047, -3.990], while gaps worsen by
  +5.955 mK [+3.919, +8.062]. The high-latitude all-support difference
  against A1 is +6.438 mK [+2.177, +10.775].

  At 50–100 km, coherence A1 → A2 improves from 0.332 → 0.422
  (Gulf Stream), 0.273 → 0.354 (Kuroshio), 0.251 → 0.327
  (Southern Ocean), and 0.023 → 0.057 (equatorial region).
  At 25–50 km A2 coherence remains near zero (≤0.016).
  Global ±60° IR observation-fit RMSE improves from 0.308 K (A1)
  to 0.297 K (A2), compared with 0.252 K for ODYSSEA.
  These observation-fit metrics are not independent validation; the
  drifter split exposes the remaining gap-filling tradeoff. CIs use
  2,000 day-block resamples, seed 42; longer temporal dependence and
  between-training-seed variability remain unquantified.

  Combined training job **1088505** failed before its first epoch with
  CUDA error 803 (driver/library mismatch). Preserve
  `t20_a2_consistency1/` as failed evidence. Slurm reported COMPLETED/0
  despite a failed FlexLock task receipt; the user is investigating
  FlexLock's exit-code handling. Inference now explicitly requires the
  training `run.complete` marker; evaluation already requires complete
  inference products. No downstream jobs were submitted for 1088505.
  The GPU partition exposes A100 and H200, not H100: an H100 probe
  submission was rejected with "Invalid feature specification" and
  accepted no job. Its attempted receipt is preserved in
  `t20_cuda_probe_20261011/`. A separate H200 probe tests inherited,
  native, and project compatibility-library paths before a fresh retry.

  **Queued H200 retry (2026-10-11):** FlexLock accepted CUDA probe
  **1089547**, fresh training **1089568** (`afterok:1089547`), and
  full-year inference **1089575** (`afterok:1089568`). Training uses
  `t20_a2_consistency1_retry1/`, preserving the failed original directory.
  Both GPU stages require successful probe completion, select a working
  library path (prefer native), and perform a CUDA allocation/synchronization
  check on their own node before starting the FlexLock worker; runtime
  selection and errors are recorded in `cuda_runtime.json`. Shell guards
  return nonzero even if FlexLock still reports scientific failures as zero.
  Training/inference use one H200, with the same scientific settings and
  resource budgets as planned; hardware differs from the historical A2 A100.
  The probe is pending at `QOSMaxCpuPerUserLimit`; downstream jobs await
  dependencies. This does not yet establish that H200 fixes CUDA.

  Launches use the public `FlexLock Project.submit(wait=False)` API via
  `scripts/submit_t20_followup.py <stage> --slurm-config <profile>` in the
  frozen project environment. Each accepted ID and exact command is saved
  in its run directory's `submission.json`. Parent receipts and task DBs
  were inspected: recoverable dirty trees cover main, FlexLock and zarrpatch,
  including new untracked runtime scripts and `pixi.lock`/`pyproject.toml`.
  Retry main tree: `879cbcac35ecb873ed6b9db839c7a387388cfe5d`;
  inference main tree: `5349440caed659bc81a379ee1d53c7d06a3af471`.
  Frozen first-guess/index/climatology/coast hashes match the failed attempt.
  Training task config verifies weight 1.0, seed 42, 50 epochs, arm B
  initialization, and logger/checkpoints under the fresh retry directory.
  Inference targets its explicit `best.ckpt` and all 365 dates; checkpoint
  SHA256 will be recorded at startup. All 56 historical scientific source
  and environment files checked against A2's recorded tree remain identical.
  Tasks are pending, so worker job IDs, resolved upstream lineage and actual
  startup receipts still need verification after allocation. Submission
  verification is complete; execution provenance verification is pending.
  Evaluation **1089595** is also queued (`afterok:1089575`) in
  `t20_a2_consistency1_evaluation_2021/`; it includes all five ML arms
  plus ODYSSEA, full-year common-support drifters, regional spectra,
  same-day IR split and 24-date observation fit/coherence. All three
  scientific stage configurations passed FlexLock's preflight check.
  Generated batch scripts passed shell syntax checks. No running jobs
  were canceled or modified to release account quota.

**P0a: fit to the same-day IR the product was given**
**Accepted next track (user, 2026-10-13):** run GIR/PIR and directional
spectra diagnostics and proceed to A3 exploration. This supersedes the earlier
requirement to wait for A2's statistical superiority over A1 before any A3
launch; production promotion still requires the common-support gate.
Record 128px/20d context tradeoff as IDEAS I27, and predictive std for
products/merging/state updates as I28. Neither new idea is trained yet.

**Consistency-1 A2 complete:** probe 1089547, training 1089568, inference
1089575 and evaluation 1089595 completed with actual FlexLock done records
and completion markers. Native H200 driver 595.71.05 initializes Torch
2.13/CUDA 12.9 successfully; the inherited project cuda-compat library
reproduces error 803. Runtime selection is recorded in the training receipt.
Full inference has all 365 outputs; explicit best.ckpt SHA256 is
`68d5672d8a64ee6121a6cbd1aab7e4093a80d3b02318a750b3b968f68f8aba33`.
Common-support global drifter RMSE is 0.446221 K vs A2 0.454916,
A1 0.455170 and ODYSSEA 0.476036 K. Global bias is -0.039915 K
(A2 was -0.000993): the RMSE improvement comes with a colder mean bias.
Paired differences vs A1: global -8.949 mK, 95% CI [-9.731,-8.143];
IR gaps -9.656 [-10.928,-8.406]; high latitudes -9.352 [-12.066,-6.669].
Latitude-band regressions vs A0/A1/A2 are absent in these RMSE results.
Outputs: `t20_a2_consistency1_evaluation_2021/followup/drifter_gate/`.
Parent and worker records were checked, including repo/environment identity
and parent links; historical source identities remain those captured then.

**Additional diagnostics complete, job 1291050:**
`sst_ml_zarrpatch/results_starter_glob/t20_sensor_direction_20261013/`.
Both GIR/PIR QL≥3 and all six ML/OI products finite on complete segments;
24 dates, 256/512 km physical windows, zonal and meridional, nearest integer
sample lengths, Hann/linear detrend. Sensor/model spectra, coverage, plots
and λ₅₀ are recorded. Common segments are comparable across products;
directions/windows necessarily have different spatial support.

For equatorial 512 km zonal windows at the saved 50–100 km frequency bins,
GIR/PIR coherence spans 0.009–0.096, and PSD(GIR−PIR)/(4 PSD(IR mean))
spans 0.60–0.90. This is a strong sensor-disagreement contribution, not a
measured pure instrumental-noise fraction: unequal sampling times, cloud
contamination, shared errors and real SST changes can violate noise assumptions.
With the same 512 km window lengths, equatorial A2 λ₅₀ is 190.1 km zonal
and 139.2 km meridional; consistency-1 is 188.5/139.4 km, and OI is
133.8/108.3 km. Meridional structure is more recoverable in this diagnostic.
These differ from the earlier 219 km zonal estimate because reference support
now requires both IR sensors and physical windows are fixed. Window sensitivity
is material: 256 km equatorial zonal A2 fails the threshold already at the
largest supported scale. Longer clear segments select different conditions;
do not attribute all direction/window differences causally to dynamics.
Worker is done/no error/job 1291050, parent links and six upstream products
resolved correctly; source tree `84e478f2e8c96a15d963499e58deebe35c7bdcc3`
contains dirty/untracked code, configuration and environment lockfile.
**Coverage qualification (recap audit, 2026-10-14):** all 24 dates were
attempted, but valid both-IR long-window coverage is highly uneven.
At 512 km, equatorial zonal/meridional support has 7,229/5,076 segments
on 24/24 dates; GS 2,609/2,767 on 24/22; Kuroshio 1,024/906 on 19/17.
Southern Ocean has only 30 zonal segments on 3 dates and 14 meridional
segments on 2 dates (256 km: 211/147 on 9/6 dates). Treat SO results as
sparse, selected-case diagnostics, not representative seasonal/regional
estimates. The new directional λ₅₀ values have no bootstrap intervals;
intervals from the earlier 32-point/any-IR stage do not transfer to them.

**A3 submitted, training job 1302535:** first two-step shared refiner with
**Training completion / budget clarification (2026-10-14):** job 1302535
has a done/no-error FlexLock task and `run.complete`; it completed all
50 configured epochs. This was a matched optimization-budget architecture
comparison, not training to convergence (nor equal GPU compute to one-step A2).
No early-stopping callback was configured. Final-iterate validation RMSE
selected best.ckpt at zero-based epoch 43: 0.451680 K; epoch 49 is
0.452865 K. Late consistency metrics continue improving, while validation
RMSE fluctuates; these results do not establish convergence. A separate fresh
continuation from last.ckpt with optimizer/scheduler state, ideally paired with
the one-step consistency-1 control, is a proposed convergence experiment and
has not been launched by this clarification.

state and visible-IR residual recomputed each step, no trajectory detachment,
activation checkpointing preserving dropout RNG, frozen arm B first guess.
Fresh arm B refiner initialization; no continued A2 training. Consistency 1.0,
seed 42, lr 1e-4, 50 epochs, 256px/5d, shuffle 256; mean of the existing
MSE+gradient+consistency losses over both iterates. Final-iterate validation
RMSE selects best.ckpt; intermediate metrics have distinct names. At K=1
the model equals A2; K=2 uses the same refiner weights, with no new step
embedding or bounded-increment architecture. Resources: one H200, 8 CPUs,
256 GiB, 48 h. Fresh run: `t20_a3_unroll2_consistency1/`.

Code/config: `model/unrolled.py`, `training/unrolled_module.py`,
`configs/t20_iteration.py`, `configs/slurm_t20_a3*.yaml`.
Three meaningful tests passed: identical-sensor/directional/missing support,
K=1 equivalence with the actual arm B checkpoint and K=2 frozen/finite
backprop, and averaged deep supervision with final-iterate metrics.
The base Lightning single-step path remains unchanged by default; an explicit
output/metric prefix permits reusing its objective for A3 deep supervision.
Logger and checkpoint paths resolve into the fresh A3 directory. Submitted
source tree is `84e478f2e8c96a15d963499e58deebe35c7bdcc3`, which contains
the new untracked scientific files and tests. FlexLock 0.9.2 is verified
in CPU and GPU environments, with the pinned wheel/environment lock recorded.
Training is pending at account GPU quota (`QOSMaxGRESPerUser`); worker startup
and final execution receipts still need verification. All scheduler launches
use FlexLock's backend via `scripts/submit_t20_followup.py` and save IDs/exact
commands in `submission.json`.
Inference **1307023** is queued with `--after 1302535`, using
`/scale/project/lops-siam-sst-ml/inference/t20_a3_unroll2_consistency1_2021_km_native_retry1/`.
Evaluation **1307503** is queued with `--after 1307023`, writing
`t20_a3_unroll2_consistency1_evaluation_2021/`. It compares all six ML arms
plus ODYSSEA on common 365-date drifter support and includes paired CIs,
IR support split, spectra and 24-date IR fit/coherence. Both scripts explicitly
check upstream completion before the worker; evaluator checks all daily outputs.
Inference records the exact new best.ckpt SHA256 at startup. Their source
snapshots and configuration paths were checked; tasks are pending and future
producer records need startup verification. An initial inference attempt mixed
the profile dependency and the new `--after` API and was rejected before any
job was accepted. Its queued-intent directory without `_retry1` is preserved
as attempted evidence, not an accepted run. The fresh launch uses only the API
dependency; the generated batch script has the correct afterok job ID.
FlexLock 0.9.2 `after` takes scheduler IDs, while the configuration retains
the exact upstream artifact paths; no direct sbatch wrapper is used.

**λ₅₀ follow-up (2026-10-13, user request):** new local FlexLock analysis
`sst_ml_zarrpatch/results_starter_glob/t20_a2_lambda50_20261013_v2/`
summarizes the saved A2 follow-up spectra without new inference or resampling.
`lambda50.csv`, `spectral_curves.csv`, `regional_context.csv`,
`methodology.json` and `lambda50.png` are the artifacts. Code/config:
`scripts/t20_resolution_summary.py`, `configs/t20_resolution_summary.py`.
λ₅₀ is the first crossing of PSD(product−IR)/PSD(IR) from ≤0.5 to >0.5
when moving from large to small zonal wavelengths. Interpolate linearly
in log wavenumber; smaller λ₅₀ is better. Unsupported scales and censored
crossings are explicitly flagged, not extrapolated. This is observation-fit
resolution, not independent reconstruction skill or a noise-corrected limit.

| Region | A0 λ₅₀ (km) | A1 | A2 | ODYSSEA/OI |
| --- | ---: | ---: | ---: | ---: |
| Gulf Stream | 96.1 | 94.2 | 86.7 | 65.1 |
| Kuroshio | 101.5 | 99.2 | 92.2 | 68.3 |
| Southern Ocean | 141.3 | 122.9 | 95.8 | 67.0 |
| Equatorial Pacific | 313.1 | 285.3 | 218.9 | 124.1 |

Conditional 95% date-bootstrap intervals for A2: GS 83.3–89.3,
Kuroshio 86.5–100.2, Southern Ocean 85.5–142.4, equatorial 189.8–284.9 km.
2,000 resamples, seed 42, 24 sampled dates; equatorial A2 has a finite
crossing in 99.4% of resamples. Equatorial A0/A1 have finite crossings
in only 64.0%/77.1%; their conditional CIs omit substantial censored mass.
Equatorial arm B already fails the threshold at the largest supported
wavelength and receives no finite λ₅₀. All crossing/censor fractions are
recorded. Physical windows, segment support and interpolation limit precision.
The first run `t20_a2_lambda50_20261013/` is retained; v2 only improves
plot tick labels and matches marker colors to curves.
Both runs completed with FlexLock 0.9.2. The v2 completion receipt, upstream
lineage, source snapshot and environment lock hash were verified; main tree
`9576cb3f5efd836da65a183794290b898a87f70f` contains the new script/config
and `pixi.lock`/`pyproject.toml`. Input SHA256s are in `methodology.json`.
V2's numerical summary is identical to v1. Launch with the project Python:
`Project('configs.t20_resolution_summary:summary').submit(...,
smart_run=False, save_dir_policy='raise')`; this is a local CPU FlexLock
stage, so no scheduler job ID applies.

**Equatorial interpretation:** the diagnostic uses a native 0.1° grid,
latitude-aware FFT spacing and interpolation of spectra to common cycles/km.
It does not resample fields into kilometre space. Physical zonal spacing
is 11.0–11.1 km near the equator, 7.9–9.6 km in GS/Kuroshio and
5.6–7.9 km in SO: this matters especially near the 25–50 km grid limit.
The model's actual kilometre patch resampler is almost identity near the
equator (stretch 1/cos(latitude); identity at 0°), making it an unlikely
primary explanation for uniquely poor equatorial coherence, although no
controlled resampler ablation has established causality.

Saved equatorial spectra have 24,164 usable segments over all 24 dates,
versus GS 13,141, Kuroshio 7,176 and SO 3,216 over 23 dates. A simple
shortage of valid segments is not supported; cloud/clear-sky selection bias
and sensor/time sampling remain possible. Segment-normalized observed
50–100 km variance is 0.002215 K² at the equator vs 0.042263 (GS),
0.034703 (Kuroshio), 0.019643 (SO), about 9–19 times weaker. The GIR−PIR
noise/representativeness reference is 0.221 K equatorial vs 0.319/0.449/0.378 K;
absolute noise is not greater, but weaker ocean structure can reduce SNR.
This reference is not a spectral noise PSD, so no scale-resolved noise
ceiling has yet been measured. OI also loses equatorial coherence, supporting
a shared signal/observation/diagnostic contribution, alongside ML attenuation.

Large equatorial structures and directional SST fronts can be poorly
represented by 32-point (~356 km equatorial) zonal, linearly detrended
windows. Tropical instability waves have characteristic zonal wavelengths
around 1,000 km ([primary study](https://journals.ametsoc.org/view/journals/phoc/49/11/jpo-d-19-0094.1.xml));
their main wavelength is outside this diagnostic. This is a plausible physical
contribution, not an attribution established by these SST spectra.
Next discriminating diagnostics: GIR/PIR cross-spectra on identical support
to estimate repeatable IR signal; zonal vs meridional spectra at matched
physical window lengths; season/latitude/sensor strata and a controlled
resampler test. These remain proposals, not launched experiments.

(`scripts/i19_p0_obs_fit.py` →
`results_starter_glob/i19_p0_obs_fit/`; 24 dates, 1st and 15th of each month,
2021). Obs-fit RMSE at IR pixels (K). The noise reference is
RMS(GIR − PIR)/√2:

| region | arm B | T18 deep | ODYSSEA | 4DVarNet-L | noise ref |
| --- | ---: | ---: | ---: | ---: | ---: |
| global ±60° | 0.321 | 0.345 | 0.252 | 0.267 | 0.256 |
| Gulf Stream | 0.532 | 0.596 | 0.388 | 0.393 | 0.319 |
| Kuroshio | 0.555 | 0.609 | 0.427 | 0.462 | 0.449 |
| Southern Ocean | 0.471 | 0.488 | 0.323 | 0.384 | 0.378 |

Coherence with the IR observations on complete 32-point IR segments
(band-integrated):

| region | band | arm B | T18 deep | ODYSSEA | 4DVarNet-L |
| --- | --- | ---: | ---: | ---: | ---: |
| Gulf Stream | 25–50 km | 0.003 | 0.000 | 0.208 | 0.552 |
| Gulf Stream | 50–100 km | 0.286 | 0.103 | 0.684 | 0.775 |
| Kuroshio | 50–100 km | 0.236 | 0.102 | 0.616 | 0.593 |
| Southern Ocean | 50–100 km | 0.190 | 0.126 | 0.642 | 0.462 |
| Equatorial Pacific | 50–100 km | 0.012 | 0.006 | 0.218 | 0.210 |

- On pixels it can see, arm B's output is essentially uncorrelated with the
  observations below 50 km. At 50–100 km it keeps about a third of
  ODYSSEA's coherence.
- ODYSSEA and 4DVarNet fit the observations to about the noise level. Arm B
  stays 25–60% above it.
- This matches the loss: visible pixels are pulled only by the consistency
  term (0.1).

**P0b: drifter RMSE split by same-day IR at the pixel**
(`scripts/i19_p0_drifter_split.py`; arm B gate matchups, 482,823 after adding
4DVarNet; bands |lat| < 20 / 20–60 / ≥ 60, so the numbers differ slightly from
the official gate):

| subset | n | ODYSSEA | arm B | T18 deep | 4DVarNet-L | raw IR obs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IR observed, all | 295,735 | 0.4043 | 0.4232 | 0.4460 | **0.3963** | 0.4469 |
| IR observed, midlatitude | 221,094 | 0.4075 | 0.4270 | 0.4512 | **0.3916** | 0.4498 |
| gap, all | 187,088 | 0.5609 | **0.5138** | 0.5224 | 1.3393 | — |
| gap, midlatitude | 143,820 | 0.5518 | 0.5035 | 0.5119 | **0.4974** | — |
| gap, high latitude | 25,880 | 0.6909 | **0.6273** | 0.6369 | 3.3874 | — |

- Arm B's whole lead over ODYSSEA comes from gaps. On IR-observed pixels it
  is 19 mK behind ODYSSEA and 27 mK behind 4DVarNet, though still better than
  the raw observation.
- **Headroom:** if arm B matched ODYSSEA on observed pixels and kept its gap
  skill, global RMSE would go from 0.460 to about 0.450 K (−10 mK). Matching
  4DVarNet would give about 0.446 K (−15 mK).
- 4DVarNet-large beats arm B at midlatitude in both observed pixels and gaps,
  but fails in high-latitude gaps (3.4 K).
- Neither 4DVarNet product has been through the official drifter gate. Add it.
- **Caveat (user, 2026-10-05): 4DVarNet was not trained on the repaired
  data.** Its high-latitude gap failure is consistent with that: on
  2021-01-15, 23% of 4DVarNet gap pixels poleward of 65° are above 290 K
  (median 279 K). This looks like the unrepaired failure fixed in T14/T17,
  not an architectural limit, so ignore its high-latitude rows. Its
  observed-pixel advantage was obtained despite the unrepaired data, which
  strengthens the reinjection case.
  - Training code not located: maxbeauchamp/4dvarnet-sst is the Baltic DMI
    setup only; CIA-Oceanix/4dvarnet-global-mapping is SSH only on every
    branch; the `renan` branch of sst_ml_mapping holds only the diagnostics
    toolbox; GitHub search was rate-limited.
  - Possible input-data confound: if it was trained on the old 0.05° 17-sensor
    L3C cube (`data/glob/ds/glob_sst_cube.zarr`, which the `renan` toolbox
    uses), it saw finer inputs than arm B.

**Arms** (all finetuned from arm B `best.ckpt`, same epochs, LR and data;
budget fixed at implementation):

- A0 control: no change.
- A1: `consistency_loss_weight=1.0`.
- A2: cascade. Frozen arm B first guess plus visible-IR misfit as two
  zero-initialised input channels. Climatology kept. New toggle, default off.
- A3: weight-shared unroll, only if A2 beats A1.

**Acceptance.** Drifter RMSE better than A0 globally (day-block CI excludes 0).
No latitude band regresses by more than 2%. Report the IR-observed / gap split
and the P0a coherence for every arm.

## Promotion template

### T<number> — Title

- **Accepted:** YYYY-MM-DD
- **Origin:** `IDEAS.md` section

**Goal:**

**Accepted scope:**

**Non-goals:**

**Baseline and controlled variables:**

**Compute budget:**

**Compatibility considerations:**

**Validation:**

**Completion criteria:**
# T7 — Independent drifter validation

**Status (2026-09-01): evaluator implemented; 12-date independent gate
complete.** Use
the daily global CERSAT/CMEMS drifter archive under
`/external/cersat9/cersat/ftp/projects/myocean/sst-tac/insitu/data/v2`. The 2021
archive has all 365 daily files; 2021-06-15 alone contains 1,461 distinct
platforms, 1,438 of which report within one hour of the noon analysis.

**Protocol:** Keep the drifters completely outside training and OI. Select
quality level >= 4, depth <= 1 m, and at most one report per
platform/day: the report closest to 12 UTC within a +/-6 h window. Evaluate the
same dates and spatial support for every candidate. Report bias, MAE, RMSE,
median error, and p90 absolute error globally and in tropical, midlatitude, and
polar bands. Stratify independently observed L4 pixels from gap-filled pixels
using the product support mask. The one-report rule is required: the archive
typically contains about 24 records per platform/day, which are not independent
replicates.

Treat `quality_level` as the archive's authoritative selection flag and retain
`rejection_flag` only as provenance. In the inspected 2021 files every accepted
quality-level-4 report carries legacy rejection value 2, so requiring a zero
rejection flag would incorrectly remove all valid drifters.

**First gate:** Run the 12 monthly 2021 validation dates against the existing
full-year baseline and OI products, then run inference for the deterministic,
no-MW-consistency, and mean/std fine-tunes on those exact dates. Promotion must
improve drifter RMSE without introducing a material regional bias. For the
probabilistic track, also export predicted sigma and assess Gaussian NLL,
68/95% coverage, and coverage-versus-latitude on these matchups.

**Implementation:** `sst_ml_zarrpatch/scripts/evaluate_drifters.py` writes both
row-level matchups and stratified summaries. It makes each platform/day one
statistical unit and records the observed/gap-filled support class for follow-up
paired comparisons.

**Initial result:** On the 12 monthly 2021 dates, 15,996 paired drifter
matchups compare the compact full-year product to the promoted R(0.8, 1.2) OI
product. OI reduces all-support RMSE from 1.342 K to 1.040 K and bias from
-0.391 K to +0.040 K. At observed pixels RMSE improves from 0.870 K to 0.496 K;
at gap-filled pixels it improves from 2.166 K to 1.844 K. The unresolved tail
is concentrated in polar gaps: OI polar-gap RMSE is 6.299 K, with several
roughly +20 K warm errors at near-freezing drifters close to sea ice. Preserve
this stratum explicitly in every promotion gate; a global score alone is not
safe. Matchups and summaries are in
`sst_ml_zarrpatch/results_starter_glob/drifter_validation_12dates/`.

**ODYSSEA L4 baseline (2026-09-01):** The same evaluator now accepts the native
daily ODYSSEA hierarchy and preserves its raw categorical mask, sea-ice
fraction, and supplied `analysis_error`. Across full 2021 it has 483,698 finite
drifter matchups: bias -0.038 K, MAE 0.289 K, RMSE 0.479 K, and p90 absolute
error 0.630 K. RMSE is 0.364 K in the tropics, 0.518 K at midlatitudes, and
0.634 K poleward of 60 degrees. Within the polar sample it is 0.569 K on the
ODYSSEA open-ocean category and 1.517 K on ice-flagged cells. The comparable
12-date score is -0.041 K bias / 0.467 K RMSE over 15,984 matchups. ODYSSEA's
mean supplied sigma is 0.753 K; empirical |error| <= sigma and <= 2 sigma
coverage are 93.1% and 98.5%, so its uncertainty is conservative relative to a
Gaussian 68/95% interpretation. Full-year row-level and summary outputs are in
`sst_ml_zarrpatch/results_starter_glob/drifter_validation_odyssea_full_2021/`.

The matched 12-date I1 gate ran, but is **invalid for production conclusions**
because all three arms warm-started from the stale epoch-0 compact checkpoint.
For provenance only, raw mean-field RMSE/bias is
1.206/+0.192 K for the deterministic fine-tune, 1.202/+0.178 K with MW
consistency disabled, 1.196/+0.091 K for the Gaussian model's mean, and
0.467/-0.041 K for ODYSSEA. Thus removing MW consistency produces only a
0.004 K pooled RMSE change (0.006 K on gap-filled pixels) in this short native
inference gate. These numbers cannot decide whether MW consistency is the main
fidelity limitation or promote the Gaussian track until the arms are rerun
from an explicitly frozen intended checkpoint. Outputs are in
`sst_ml_zarrpatch/results_starter_glob/drifter_gate_i1_12dates/`.

### Provenance clarification and next research proposal

The user notes that FlexLock provenance is in the SQLite database. Do not infer
missing provenance from a minimal parent receipt or one snapshot field: inspect
the complete database and referenced records before reaching that conclusion.
The earlier assertion that T12/T15 repository identity was missing is not a
settled finding. Both runs used FlexLock. Continue to use it and verify provenance
as required by root `AGENTS.md`.

Climatology dropout and complete ablation are recorded as **I13** in
[IDEAS.md](IDEAS.md#i13--climatology-dropout-and-ablation-after-t15), including
both explicit climatology channels and missing-observation fill values. This is
a research proposal; experiment details and budget remain to be specified.
