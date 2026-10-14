# TODO

Accepted next work only. Promote an item from [IDEAS.md](IDEAS.md) after its
scope, comparison, and success criterion have been agreed. Completed work and
decisions move to [DONE.md](DONE.md).

## Active

T1–T4 are complete. T3's missing control and matched 64-per-category comparison
finished on 2026-08-04; results and the resulting decision are recorded in
[DONE.md](DONE.md#m1-t3-conditioning-matrix-completed-2026-08-04). T4 completed
as job `3167676` on 2026-08-18; its final comparison is recorded below.

### T5 — LeJEPA E1: coupled ocean–atmosphere encoder vs atmosphere-only

- **Accepted:** 2026-10-11
- **Origin:** [IDEAS.md I11](IDEAS.md#i11--self-supervised-lejepa-representation-of-the-coupled-storm-state)

**Goal:** First self-supervised encoder of the coupled storm-centred state; measure whether
its embedding carries intensity-evolution and ocean-response information, and what the
ocean channels add.

**Accepted scope:**

- corpus `scripts/lejepa/build_corpus.py` → `/scale/scratch/qfebvre/nextgems_lejepa/v1`:
  every 6-hourly fix of the 9,710 usable `nextgems_preproc/v1` storms (313 k frames;
  train ≤ 2039 / val ≥ 2040), 128 px × 10 km, 15 channels — `10u 10v msl 2t tcwv ttr slhf
  sshf log1p(tp6h)`, `tos zos sos mlotst125`, `dtos` (tos − fixed pre-storm tos), ocean mask;
  per-fix probe scalars in `*_meta.parquet`;
- trainer `scripts/lejepa/train.py`: hafs-jepa faithful frame recipe, ViT-S/16, 60 ep,
  bs 256 × 4 views, z-space views (RRC 0.08–1, vector-aware flips, blur);
- probes `scripts/lejepa/probe.py`: ridge on frozen CLS, val storms.

**Experiment matrix** (`sbatch nextgems_tc/slurm/lejepa_e1.sbatch`):

| Array | Run | Channels |
|---:|---|---|
| 0 | `e1_coupled` | all 15 |
| 1 | `e1_atmos_only` | 9 atmosphere |

**Baseline and comparison:** `scalars` (vmax, msl, |lat|, motion, past-24 h Δvmax, pre-storm
tos and MLD) versus `scalars+hist` (plus CLS at t, −6, −12, −24 h) on Δvmax 24/48 h, Δmsl
24 h, wake dSST at +24/+48 h; coupled versus atmos-only on the same table. State targets
(vmax, msl, Rmax, wake now, pre-storm ocean) check that the encoder is not collapsed — the
`scalars` column is trivially 1 for the targets it contains.

**Non-goals:** no temporal objective, no fusion, no generative use yet.

**Validation:** loss curves (invariance should fall to ≈ 0.05–0.1 as on HAFS; ≈ 0.6 is the
collapse signature); vmax R² from `emb`.

**Completion criteria:** probe tables for both arms. E1 is positive if `scalars+hist` beats
`scalars` on Δvmax or future wake; the ocean matters if coupled beats atmos-only on the
same targets (paired storm bootstrap before claiming it).

**Result (2026-10-13):** job `1089609` completed on compute-117-39 (H200), 2.5 h / 2.1 h.
Both arms trained cleanly (no NaN; final inv 0.0048 / 0.0077, SIGReg 0.45 / 0.48; vmax
from `emb` R² 0.90 / 0.93, so no collapse). Val R², ridge on `scalars` (+ current wake) vs
`scalars + CLS history`, paired storm bootstrap (500×, `runs/lejepa/e1_bootstrap.csv`):

| Target | scalars | + coupled | + atmos | coupled − atmos [95 % CI] |
|---|---:|---:|---:|---|
| Δvmax 24 h | 0.151 | 0.400 | **0.444** | −0.043 [−0.052, −0.035] |
| Δvmax 48 h | 0.229 | 0.480 | **0.501** | −0.021 [−0.032, −0.012] |
| Δmsl 24 h | 0.158 | 0.435 | **0.482** | −0.047 [−0.056, −0.038] |
| wake +24 h | 0.522 | **0.612** | 0.585 | +0.027 [+0.021, +0.033] |
| wake +48 h | 0.315 | **0.419** | 0.379 | +0.040 [+0.030, +0.051] |

E1 is positive: the embedding history roughly triples the explained variance of intensity
change over track/persistence scalars (+0.25 to +0.32). The ocean question splits:
ocean channels in a *joint* encoder **cost** intensity-change skill, but **add** to the
future ocean response even with the current wake given as a scalar. Next: late fusion
(atmos encoder + ocean-only encoder), which tests whether the ocean adds to Δv when it does
not compete for the joint encoder's capacity.

### T4 — Combined center weighting and Vmax loss, with a calibrated target

- **Accepted:** 2026-08-17
- **Completed:** 2026-08-18
- **Origin:** T3 decision plus the within-category diagnostic added the same day
  (see [DONE.md](DONE.md#within-category-conditional-skill-2026-08-17))

**Goal:** Establish whether the two interventions that beat control combine, and
remove the systematic upward push in the auxiliary Vmax target.

**Accepted scope:**

- uniform flow time, legacy conditioner, patch 4, and the T2 stability settings
  are fixed for every member, so only the auxiliary-loss treatment varies;
- an auxiliary target scale, because the conditioning scalar is the frame
  maximum wind while the supervised statistic is a top-16 mean that is only
  0.93–0.95 of it in the training data — the current target is unreachable and
  is the likely cause of `vmax_loss` over-intensifying TD/TS by ~3.5 m/s;
- an alternative intensity ramp that removes the auxiliary term below TS
  intensity instead of rescaling it;
- a within-category skill metric reported for every evaluation.

**Experiment matrix:**

| Array | Run | Single change from member 0 |
|---:|---|---|
| 0 | `combo` | none — center weight 3 + Vmax loss 0.1 |
| 1 | `combo_calib` | auxiliary target scale 0.935 |
| 2 | `combo_ramp` | auxiliary weight ramp 25→43 m/s |
| 3 | `combo_dropout` | 10% condition dropout (exploratory) |

Member 3 is exploratory rather than accepted: CFG 3 was rejected on structure,
not on mechanism, and the new metric shows dropout with guidance is the only
T3 intervention that improves per-storm skill. Its guidance strength must be
selected from the separate identical-noise sweep, never from the panel.

**Execution:**

```bash
sbatch nextgems_tc/slurm/m1_combo_experiments.sbatch
```

**Baseline and comparison:** the exact 64-per-category panel in
`runs/m1_consolidated`; `center_weight` (slope 0.732, MAE 7.87) and `vmax_loss`
(slope 0.850, bias +1.03) are the references to beat.

**Non-goals:** no architecture, patch-size, or schedule change.

**Validation:** identical panel, seed, noise, and solver as
`runs/m1_consolidated`, plus the new `within_category_skill.csv`.

**Completion criteria:** a member beats both references on pooled bias and MAE
*without* regressing pooled within-category correlation, and does not inflate
C4–C5 R34 beyond the real 185–195 km. Pooled metrics alone are no longer
sufficient evidence.

**Result:** all four members trained stably through 30k steps and were evaluated
on the fixed 64-per-category panel at CFG 1. The final comparison is:

| Run | Vmax slope | Correlation | Bias (m/s) | MAE (m/s) | Within-cat corr | C4/C5 R34 (km) |
|---|---:|---:|---:|---:|---:|---:|
| `combo` | 0.983 | 0.945 | +1.55 | 5.14 | 0.372 | 160 / 155 |
| `combo_calib` | 0.842 | **0.952** | -3.23 | 5.27 | **0.398** | 165 / 160 |
| `combo_ramp` | **1.010** | 0.948 | **+0.49** | **4.97** | 0.354 | 165 / 155 |
| `combo_dropout`, CFG 1 | 0.861 | 0.909 | -0.85 | 6.25 | 0.311 | 165 / 155 |

The intensity ramp is the accepted winner. It beats both T3 references on
absolute bias and MAE, improves pooled within-category correlation over
`center_weight` (0.273) and `vmax_loss` (0.162), and does not inflate major-
storm R34 relative to the real C4/C5 medians of 195/185 km. The unscaled
combination is also strong but misses the bias criterion. Scaling the target to
0.935 overcorrects into a -3.23 m/s bias and restores strong-storm low bias;
the ramp is therefore preferable to global calibration.

The exploratory dropout member at CFG 1 also clears the numerical completion
threshold, but it is not promoted: its MAE and within-category correlation are
worse than the ramp's, and no guidance strength was selected and evaluated on
the held-out panel as required. All four members still have negative pooled
within-category R² (best is `combo_calib` at -2.97), so none reproduces
storm-to-storm intensity variation adequately.

### T3 — M1 conditioning foundation and ablation matrix

- **Accepted:** 2026-07-30
- **Origin:** `IDEAS.md` I7 plus transferable practices from `maxss-ml`
- **Completed:** 2026-08-04 — see
  [DONE.md](DONE.md#m1-t3-conditioning-matrix-completed-2026-08-04)

**Goal:** Determine which interventions improve strong-storm conditional
fidelity without confounding architecture, optimization, or model selection.

**Accepted foundation:**

- independently configurable uniform/logit-normal flow-time sampling;
- legacy or per-scalar Fourier conditioning with a dedicated null embedding;
- per-sample conditioning dropout and classifier-free guidance sampling;
- normalized Gaussian inner-core loss weighting;
- robust top-16 physical Vmax supervision on predicted-clean fields, with
  stronger penalty for under-intensification;
- fixed-noise, intensity-stratified sampled validation during training;
- separate `best_flow.pt` and physically selected `best.pt`;
- identical-noise Vmax/CFG sweep after training;
- all settings serialized in each run's `config.json`.

**Experiment matrix:**

| Array | Run | Single change from control |
|---:|---|---|
| 0 | `control` | none |
| 1 | `logit_time` | logit-normal `t` |
| 2 | `fourier_condition` | separate Fourier scalar conditioner |
| 3 | `center_weight` | 3× Gaussian inner-core emphasis |
| 4 | `vmax_loss` | robust asymmetric Vmax loss, weight 0.1 |
| 5 | `cond_dropout` | 10% per-sample condition dropout |
| 6 | `combined` | all five interventions |

All runs share seed 0, BF16, patch 4, batch 64, LR 2e-5, 1k warmup, 30k
steps, EMA 0.999, and identical validation/sampling seeds.

**Execution:**

```bash
sbatch nextgems_tc/slurm/m1_foundation_experiments.sbatch
```

**Primary comparison:** balanced-panel conditional Vmax MAE and slope from
`best.pt`, with the existing `m1_dit_full/best.pt` and matrix `control` as
references.

**Secondary comparisons:** validation flow loss, category-wise bias, radial
profiles, finite-R34 fraction, channel quantiles, identical-noise response
slope, and CFG response. For dropout models, select CFG strength without using
the final held-out scientific comparison.

**Non-goals:** No patch-2 or U-Net/log-polar architecture change in this
matrix. Those alter compute and capacity too strongly for a clean foundation
ablation.

**Completion criteria:** all seven configurations finish or produce actionable
failure diagnostics; each intervention is compared to control using the fixed
metrics; only improvements that beat both control and the original checkpoint
are candidates for a larger architecture experiment.

**Execution snapshot (2026-08-04):** Array members 1–6 ran as job `2630345`.
`fourier_condition`, `center_weight`, `vmax_loss`, and `cond_dropout` completed
30k steps and produced post-training evaluations. `logit_time` aborted at step
14,311 with gradient norm 106; `combined` aborted at step 18,010 with gradient
norm 109. Both failures are actionable evidence against logit-normal time
sampling under the current optimizer and guard. No `control` output or array-0
log exists, so intervention effects cannot yet be isolated from the new
training foundation.

The provisional 32-per-category balanced-panel results from physically
selected `best.pt` checkpoints are:

| Run | Vmax slope | Correlation | Bias (m/s) | MAE (m/s) |
|---|---:|---:|---:|---:|
| Original `m1_dit_full` (64/category reference) | 0.371 | 0.797 | -17.55 | 17.95 |
| `fourier_condition` | 0.459 | 0.840 | -15.81 | 16.41 |
| `center_weight` | 0.722 | 0.938 | -7.59 | 8.31 |
| `vmax_loss` | **0.871** | 0.856 | **+0.76** | **7.86** |
| `cond_dropout`, CFG 1 | 0.412 | 0.804 | -15.64 | 16.22 |

The robust asymmetric Vmax loss is the leading intervention: it largely
removes pooled intensity bias and prevents C1–C5 saturation, although it
slightly over-intensifies TD/C1 and within-category correlations remain weak.
Inner-core weighting is the second useful intervention, but retains a strong
C5 low bias and its training deteriorates after roughly step 24k. Fourier
conditioning alone gives only a small improvement. These conclusions are
provisional until the matrix control is evaluated on the identical panel.

Dropout at CFG 1 should not be rejected yet. Its separate identical-noise sweep
improves from slope 0.342 and MAE 21.45 m/s at CFG 1 to slope 0.897 and MAE
7.08 m/s at CFG 2, and slope 1.123 and MAE 5.14 m/s at CFG 3. Select a CFG
setting on the non-held-out sweep, then run the balanced panel once at that
fixed setting. Guidance results from models trained without dropout are not a
valid basis for selection because their null-conditioning path was untrained.

**Completed follow-up:**

1. Matrix `control` trained to 30k steps and was evaluated on the fixed panel.
2. `cond_dropout` was fixed at CFG 3 from its separate sweep and evaluated.
3. `m1_dit_full/best.pt` was re-evaluated at the same 64/category support.
4. The evaluator produced the fixed structural diagnostics for every candidate.
5. `center_weight` and `vmax_loss` beat both exact references; the next proposal
   is a uniform-time combination of those two interventions.

### T1 — Repair and strengthen M1 evaluation

- **Accepted:** 2026-07-29
- **Origin:** `IDEAS.md` I2 + I6
- **Completed:** 2026-07-30 — see
  [DONE.md](DONE.md#m1-evaluation-and-stability-experiments-2026-07-30)

**Goal:** Make conditional fidelity and storm structure measurable enough to
select M1 checkpoints reliably.

**Accepted scope:**

- build a fixed-seed, intensity-stratified validation panel with adequate
  representation of C1–C5;
- report generated Vmax versus conditioned Vmax slope, correlation, bias, and
  MAE overall and by category;
- add centre-error and radial-profile diagnostics;
- report the finite-R34 fraction before comparing R34 values;
- report channel-wise physical quantiles for real and generated fields;
- repair the OLR montage scaling or label so it is interpretable;
- evaluate existing checkpoints where available.

**Baseline and comparison:** Compare against `runs/m1_dit_full/best.pt` and the
existing 512-sample evaluation: Vmax correlation 0.710, bias −2.12 m/s, MAE
3.70 m/s, and finite-R34 fractions 2.7% generated versus 17.9% real.

**Non-goals:** No model architecture or training-distribution change in T1.

**Validation:** Fixed conditions and random seeds must make checkpoint
comparisons repeatable. Category labels remain based on conditioning Vmax.

**Completion criteria:** A single evaluation command produces the stratified
metrics and diagnostic figures, and makes strong-storm conditional failure
visible without relying on a pooled histogram.

### T2 — Stabilize M1 training

- **Accepted:** 2026-07-29
- **Origin:** `IDEAS.md` I1
- **Completed:** 2026-07-30 — see
  [DONE.md](DONE.md#m1-evaluation-and-stability-experiments-2026-07-30)

**Goal:** Identify and prevent the optimization failure that begins after the
useful step-6,000 regime.

**Accepted scope:**

- reproduce the run initially with the same seed and capture the first spike;
- add finite-value checks and diagnostics sufficient to associate spikes with
  input channel, conditioning tail, flow time `t`, parameters, and optimizer
  state;
- compare short 10–15k-step runs using a smaller learning rate and warmup;
- include a short FP32 control to test whether BF16 contributes;
- retain gradient clipping but do not treat clipping alone as stabilization;
- evaluate candidate checkpoints with T1.

**Baseline and comparison:** The current 22.4 M-parameter run has best EMA
validation loss 0.1423 at step 6,000, maximum pre-clipping gradient norm 3,129
by step 8,000, later maxima up to 123,200, and terminal validation loss near
1.09.

**Non-goals:** No larger model, full 60k-step production run, or category
reweighting until the instability is understood.

**Validation:** Compare loss curves, pre-clipping gradient statistics,
non-finite diagnostics, and T1 conditional metrics across identical seeds and
validation panels.

**Completion criteria:** At least one configuration reaches 10–15k steps
without the observed loss/gradient collapse and retains or improves the
step-6,000 baseline on T1 metrics.

## Next decision

Use `combo_ramp/best.pt` as the M1 checkpoint from T4. The ramp resolves the
pooled intensity target without the calibrated member's strong-storm
under-intensification, but its within-category correlation is still only 0.354
and its within-category R² is -5.20. The next proposal should target the
conditioning pathway rather than further tuning the auxiliary loss — see
[I9](IDEAS.md#i9--the-open-failure-is-within-category-intensity-skill).

## Promotion template

### T<number> — Title

- **Accepted:** YYYY-MM-DD
- **Origin:** `IDEAS.md` section

**Goal:**

**Accepted scope:**

**Baseline and comparison:**

**Non-goals:**

**Validation:**

**Completion criteria:**
