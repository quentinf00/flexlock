# TODO

> **⚠ P0 (2026-09-24): SAR `wind_dir` is "from", scatterometers "towards" — all Phase-C real-SAR
> u/v targets were built with reversed direction.** See [P0 below](#p0--highest-priority-sar-wind-direction-convention-bug-found-2026-09-24).
> Fix before any new real-data training or structure-based evaluation.
> **⚠ P0b: the sim "BT" channel (param 64) is SSMIS 91 GHz microwave, not IR**; the IR-window match for
> IRAR is param 58 (ABI B13). All btir models trained on the wrong channel. See P0b below;
> **action P0b.1 (handoff, owner to assign): retrain the 24 h dense-BT chain on band 13.**

Active workstreams only. Detailed design lives in the linked plan docs; completed
milestones and durable decisions move to [done.md](done.md); speculative follow-ups
live in [ideas.md](ideas.md). Convention (CLAUDE.md): one slug per hypothesis, configs
in `maxss_configs/` registered in `index.md`, new params default to old behaviour.

Master roadmap: [unified_reconstruction_plan.md](tracks/unified_reconstruction_plan.md).
Living results: [unified_reconstruction_results.md](details/unified_reconstruction_results.md).

## Planning document map

Active scientific tracks:

- [Unified reconstruction roadmap](tracks/unified_reconstruction_plan.md)
- [Direct-flow-TC consolidation](tracks/direct_flow_tc_consolidation_plan.md)
- [Phase-C real-SAR fine-tuning](tracks/phase_c_sar_finetune_plan.md)
- [Conditional neural field (I28)](tracks/neural_field_plan.md) — branch `neural-field`
- [24-hour BTIR/HAFS pretraining and BT-only parity investigation](tracks/btir_24h_hafs_pretraining_plan.md)

Supporting details and presentation material:

- [Executed storage cleanup (2026-10-14)](details/storage_cleanup_2026-10-14.md) — 72.79 GiB of file allocation removed; duplicate checkpoint aliases preserved; [early dataset retirement](details/retired_early_datasets_2026-10-14.md) documented.
- [Git snapshot stripping and canonical reference-data storage](details/git_and_reference_storage_2026-10-14.md) — read-only rewrite preview: 40 affected FlexLock refs; 101.21 GiB of completed local reference products eligible for shared relocation, with compatibility links.
- [Experiment tiers and deterministic baseline](details/experiment_tiers_and_deterministic_baseline.md)
- [Unified reconstruction results](details/unified_reconstruction_results.md)
- [Latent-space design reflection](details/latent_space_reflection.md)
- [Project journey report](details/project_journey_report.md)
- [Mid-term meeting report and narrative](details/midterm_meeting_report.md)

Superseded notes remain under [`archive/`](archive/); they are historical context,
not active execution scope. The temporal / sequence-FM track (P3.1) was parked on
2026-09-05 and moved to
[archive/temporal_sequence_fm.md](archive/temporal_sequence_fm.md) — three T=8
architectures all degraded field and intensity skill, so the temporal problem will be
reconsidered fresh rather than resumed. `unified_reconstruction_plan.md` §P3.1
remains the design reference if it is picked up again.

Anggrek diagnostics completed (2026-08-20): the 23 SAR-time source ablations,
corrected external-GEO-IR BT/no-BT comparison, and four 171-frame 3-hour lifecycle
runs (unguided, scatterometer-guided, radiometer-guided, and both-guided) are
finished and scored against IBTrACS. Results are recorded in
[unified_reconstruction_results.md](details/unified_reconstruction_results.md).
The public HTML report refresh is **done** (2026-09-04): both
`tcwind_benchtools/results/anggrek_report/` and `results/midterm_report/` were
rebuilt, the stale pre-overwrite `ablation_nosar` score was replaced by a fresh
re-score of the current dump, and the temporal-consistency plot is regenerated.

Mid-term reporting update (2026-09-04): the accessible student reconstruction at
`/scale/project/ifremer-isi-jumeaunumerique/tcwind_solutions/unetsargeo/temporal_mean_24h_deltas_v00`
has been integrated into a common Anggrek lifecycle report despite the separate blocked
training-artifact directory. It scores Vmax RMSE/bias/MAE 5.44/-0.17/3.72 m/s over
192 pairs, but R34 bias/MAE is +65.03/+65.03 km over 178 pairs. The static report and
frozen Phase-C scatter panels live in `tcwind_benchtools/results/midterm_report/`.

Measurement-guidance correction completed (2026-08-20): the earlier lifecycle
runs used source-aware conditioning but their dense guidance residual only
block-averaged retrievals onto the 6-km model grid. Implement and validate the
missing observation operator: convolve generated winds to the native
ASCAT/HSCAT/SMAP/SMOS footprint, weight residuals by source uncertainty, and use
a one-sided likelihood above a calibrated scatterometer saturation threshold.
Keep the historical operator available for exact reproduction. Sensorcal v1 is
now frozen from `ft_sar_v1/train`: sigma(SAR/scat/rad) = 1.00/1.875/2.117 m/s;
the pooled scatterometer hinge bends at SAR-equivalent 29.0 m/s, or observed
22.684 m/s. Corrected joint SAR+scat+rad Anggrek lifecycle job 3232139 completed
on 2026-08-20. Sensor-calibrated joint guidance is the best recorded lifecycle
variant (Vmax RMSE 13.96 m/s; R34 MAE 37.48 km), but the improvement over
unguided remains modest and the negative intensity/size bias persists.

Consolidation decision (2026-08-25): use reusable smoke/proxy/confirmation/native
tiers and establish a deterministic eight-frame BTIR + observation-token baseline
before launching more loss/architecture variants. Plan and gates:
[experiment_tiers_and_deterministic_baseline.md](details/experiment_tiers_and_deterministic_baseline.md).
Deterministic smoke job 3404828 passed the execution/learning-sanity gate. The
matched 128² proxy job **3438070** completed in 2 h 46 min: field RMSE improved
from 7.954 to a stable minimum of 2.740 m/s at step 8,500, while Vmax error
bottomed near 7.36 m/s and then drifted upward. Full-stream confirmation job
**3454480** (`det_btir24h_confirmation_001`) completed successfully after reaching
field RMSE 2.061 and Vmax error 5.324 m/s by step 111,347. Matched real-SAR
fine-tune job **3484203** completed all 4,080 configured steps in 4 h 51 min after
its real-data 16-channel contract passed. Its best/final validation field RMSE is
3.1898 m/s and Vmax error is 10.0787 m/s. Frozen one-pass test job **3507425**
completed all 526 acquisitions and 3-hour Anggrek lifecycle job **3507426**
completed all 171 frames; both exited successfully.

Scoring completed on 2026-08-31. On the frozen test, the deterministic model has
field RMSE 3.2216 m/s, bias -0.6033 m/s, CRPS 2.2886 m/s, radial-profile MAE
2.2999 m/s, Vmax MAE 5.6316 m/s, and Rmax MAE 44.9238 km. Spread/calibration
metrics are undefined by design for its single member. This is worse than the
available flow references (`ftsar_all_test`: RMSE 2.6895, Vmax MAE 5.3325,
Rmax MAE 43.3810; `ftsar_btir_unet_test`: RMSE 2.9135, Vmax MAE 4.8673, Rmax
MAE 44.0190), so it does not pass the confirmation gate and must not advance to
native resolution. The exact 24-hour dense-BT flow checkpoint has not yet been
dumped on this test, so this is strong rejection evidence rather than a perfectly
conditioning-matched ablation.

Against IBTrACS over the Anggrek lifecycle, deterministic Vmax RMSE/bias/MAE is
12.0719/-10.1102/10.1102 m/s (162 pairs) and R34 mean RMSE/bias/MAE is
71.8763/-43.3291/56.8197 km (132 pairs). It improves Vmax RMSE over the existing
token-BT flow lifecycle (14.9314 m/s unguided) but substantially worsens R34 MAE
(41.3424 to 56.8197 km); this is not a lifecycle win.

---

## P0c — HAFS cycle identity and downstream checks after wind-time repair (2026-09-30)

**Historical-join checks run 2026-09-30:** source repair verified 470/470; derived timestamps
match source 468/468 per tier; denylist identical. The old MAXSS joins fail:
`v1` filtered training has 432/4,429 wrong ATCF joins and 28 missing joins;
422/4,350 resolvable wind–BT pairs have different initialization times.
Validation: 38/613 wrong ATCF joins, 14 missing; 38/599 wrong BT times.
Report and reproducible audit: [cycle identity checks](details/hafs_cycle_identity_checks.md).
**Correction implemented:** timestamp ATCF joins and grid-verified BT mappings in
main and NF loaders; 297,269 ATCF frames verified, 217 unresolved cycles rejected.
Matched and balanced flow panels plus NF B13 frame/sequence caches refreshed under
`.cycles_v2` names. Four targeted NF-worktree tests pass; corrected-data training
and transfer experiments remain open. All 62 eligible missing shard members were
restored on 2026-10-01; [T8 completion](done.md#t8--missing-hafs-shard-members-restored-2026-10-01).

Upstream dependency: hafs-jepa T8 (archived in its `plans/DONE.md`)
and its [repair record](../../260324_jepa/hafs-jepa/plans/DONE.md#wind-init_time-repaired-dynamics-baselines-2026-09-30).
T8 item 1's derived Zarr repair is verified; item 3's MAXSS loader fix is now
implemented here. Item 4's shared shard restoration is complete. Existing
trained checkpoints retain their historical input pairings.
The repair changes timestamps only: wind arrays remain byte-identical.

**Corrected B13 chain queued 2026-10-02:** HAFS `175299` → intense `175300`
→ corrected-SAR `175301`, with `afterok` dependencies and fresh `cycles_v3`
directories. Frozen configs, source snapshot, manifest and checks:
[retraining record](details/hafs_cycles_v3_retrain.md). Historical seed was not
recorded, so this is a matched-recipe rerun rather than a proven seed-paired
estimate of the repair's effect.
**2026-10-04:** all three jobs completed; separate 100-epoch continuation
`353943` queued. Parent `last.ckpt` is stale at epoch 0, so this branch must
repeat earlier epochs. SAR's nested logger/checkpoint paths pointed into the
old `intense_p0` directory; identify/preserve the new artifacts before scoring.
The source relocation helper is fixed; frozen submitted inputs remain intact.
**2026-10-05:** SAR checkpoint verified and preserved in the corrected run
directory. Full frozen 526-acquisition OSE inference `379229` and dependent
score/scoreboard-report update `379230` queued; results remain pending.
**2026-10-06:** continuation `353943` cancelled after validation epoch 48:
best RMSE remains 3.122 at epoch 1, latest 4.013, and epochs 39–48 show no
sustained improvement. Checkpoints/metrics retained; full OSE jobs retained.
See the retraining record for the diagnostics and learning-rate limitation.

The upstream audit measured **872 / 7,477 labelled wind cycles (11.7%)** assigned
another cycle's ATCF labels by our sorted-index join, plus 161 out-of-range
indices. This is archive-wide exposure, not a measured rate for each training
split or a measured BT-pairing error rate.

- [x] **Verify upstream completion and fix cycle identity before new HAFS-conditioned
  training.** Map each wind shard's `(storm, init_time_idx)` to its repaired source
  initialization timestamp; join ATCF by `(storm, actual init_time, lead_hours)`.
  Honour the unresolved-cycle sidecar rather than assigning another cycle's labels.
  Cover the main flow loader, raw-Zarr loader and copies in the neural-field
  worktree. Retain original indices for reproducing historical artifacts.
- [ ] **Measure exposure on our actual splits and panels.** Count changed, missing,
  unresolved and out-of-range joins by train/validation/test split, storm and
  field-Vmax band. Quantify changes in Vmax, R34, motion and center coordinates;
  check lead-0 nest/track alignment. Record affected runs and their saved data
  paths/configs, including whether they use repaired source or stale derived stores.
- [x] **Audit wind–BT pairing independently.** The historical flow `BtirHook` and neural-field
  `iter_shard_frames` matched numerical cycle indices across modalities.
  Verify actual initialization times and native grids for each pair; use explicit
  timestamp-based pairing where indices differ. Measure missing/mismatched pairs
  for single-frame and 24-hour BT contexts. Do not infer this rate from the 11.7%
  ATCF-label figure. Recheck pseudo-observation geographic coordinates after the
  center correction; their wind values/directions come from the target field.
- [x] **Refresh affected evaluation artifacts with provenance.** Check validation
  membership against T8 item 4, then rebuild caches/panels that contain wrong ATCF
  metadata or BT pairs. Preserve old artifacts for paired reproduction; record
  added/removed cases separately. Field-derived Vmax inventories and wind-only NF
  targets need rebuilding only if their fields, membership or keys change.
- [ ] **Run a controlled corrected-data comparison.** Hold architecture, training
  budget, seeds, sensor operators and the P0/P0b direction/channel fixes constant.
  Compare a representative ATCF-conditioned flow baseline and, if pairing errors
  are found, the BT-conditioned flow/NF head. Score field RMSE/CRPS, per-member
  Vmax bias/MAE, R34, direction and conditioning adherence by intensity band on
  matched cases. Establish the effect before attributing existing biases to this bug.
- [ ] **Check transfer through corrected pretraining.** For a corrected HAFS parent,
  repeat the matched real-SAR fine-tune and frozen real evaluation/Anggrek lifecycle.
  Real acquisition-time joins are independently built and remain directly valid;
  this check measures inherited pretraining effects. Update the result ledger with
  measured changes and decide which historical comparisons need rerunning.
- [ ] **Revisit temporal consistency with corrected cycle pairings.** Reassess the
  parked sequence-flow ideas in `archive/temporal_sequence_fm.md` and the NF temporal
  results after the corrected B13 chain establishes a baseline. Use restored,
  timestamp/grid-matched 24-hour panels; compare historical and corrected models
  on identical cases and report restored cases separately. Require field and
  per-member intensity skill alongside fixed-noise temporal coherence before
  promoting another temporal experiment. The join repair motivates a new check;
  its effect on earlier temporal conclusions remains unmeasured.

## P0 — HIGHEST PRIORITY: SAR wind-direction convention bug (found 2026-09-24)

**Queued 2026-09-24:** corrected-target token and intensity-token fine-tunes,
plus matched B13/param-64 24 h HAFS→SAR chains and test/Anggrek rescoring.
Slurm IDs and comparison protocol: [P0/P0b rerun ledger](details/p0_direction_b13_rerun.md).
The legacy SAR target remains the default for historical run-lock reproduction;
the new jobs explicitly opt into `sar_wind_from=True`. Scoring now includes
vector RMSE, direction MAE and rotation-sense rate wherever SAR direction is
available. Results are pending. The 2026-09-25 H1 retry and scorer dependency
repair are recorded in the ledger.

**Blocks:** every real-data result that depends on field *structure* (Phase C, the D track, E3 of the neural-field track). Resolve before any new real-data training or evaluation.

**Finding.** V04 SAR `wind_dir` is meteorological "from"; all scatterometer sources are "towards"
(the user's note; the compiled V04 files keep no convention attribute, only `units: degree`).
Physical test (`scratchpad/dir_convention.py`): converting with the "towards" formula
`wdir_to_uv` (u = s·sin d, v = s·cos d), the mean tangential wind has the correct
hemisphere sign in **0/38** SAR files, against 25/26, 24/25, 24/25, 34/34 and 28/28 for
ascata/b/c and hscat2b/c. `obs_v04.wdir_to_uv`'s docstring says to add 180° for
wind-from, but `sar_finetune_datamodule.py:164` calls `wdir_to_uv(spd, wdir)` on SAR
directly. So **every Phase-C real-SAR u/v target is negated**: reversed circulation, and
inflow turned into outflow.

**Evidence the models learned it** (rotation sense of member 0 on the frozen test,
`scratchpad/dump_sense.py`, 66 sampled cases): `ft_det_btir24h_test` 2% correct,
`irreg_radial_test` 2%, `ftsar_all_test` 36%, `ftsar_btir_tok_cfg1p5_test` (selected) 47%,
`uobs_btir_tok_test` (warm start, pre-Phase-C) 64%.

**Why the scoreboard never showed it:** real-test truth and scores are speed-only
(`_write_wspd` scores `hypot(u, v)`), which is invariant to negation. The Anggrek/IBTrACS
lifecycle scores are also speed/radius-based.

**Also:** the warm start is only 64% correct. Sim-trained models apparently cannot get the
sense from latitude (legacy flips mirror the field without touching lat/lon or hemisphere
metadata), so the sense must come from direction tokens, and without scat in the window it
is close to a coin flip. Related NF finding: [speed-only identifiability](tracks/neural_field_plan.md).

**To decide (user):**
- [ ] Fix the conversion per source (SAR: +180°) in `obs_v04` / `sar_finetune_datamodule`
      (default must reproduce old runs → explicit flag or per-source convention table).
- [ ] Re-run Phase-C fine-tuning for the selected / key variants with corrected targets.
      Re-score: speed metrics may barely move, so add a **vector / direction** metric
      (rotation-sense rate, u/v RMSE, inflow angle) to benchtools before comparing.
- [ ] Audit every other `wind_dir` consumer (V04 tokens use `dir_groups=("scat",)` by default,
      so SAR direction tokens were not used; verify the eval harness and any plots).
- [ ] Give the sim prior the hemisphere: sign-aware flips (flip ⇒ mirror latitude/hemisphere
      token) or a hemisphere token, so the rotation sense is no longer a coin flip without scat.

---

## P0b — HIGHEST PRIORITY (with P0): the "BT" channel used by every btir model is 91 GHz microwave, not IR (found 2026-09-24)

**Action → [P0b.1 handoff](#p0b1--handoff-another-person-retrain-the-24-h-dense-bt-chain-on-abi-band-13):
retrain the 24 h dense-BT chain on ABI band 13 (param 58, index 3).** Owner: to assign. The
neural-field track takes the BT-output-head work (I31) separately.

HAFS `webds/sat` channels are NCEP local GRIB2 table 4.2-3-192 parameters (checked against the
NCEP table and the bucket's `.idx` inventories): 53/54/55 = GOES-R ABI bands 8/9/10 (6.2/6.9/7.3 µm
water vapour), **58 = ABI band 13 (10.3 µm clean IR window)**, 62/63 = SSMIS-F17 ch15/16 (37 GHz H/V),
**64 = SSMIS-F17 ch17 (91.655 GHz V)**, 65 = ch18 (91.655 GHz H). `BtirHook(token_channel=6,
dense_channels=(6,))` selects param **64**, so `uobs_btir_*`, `ftsar_btir_*`, the 24 h dense-BT chain
and the D-track IR models were **trained on simulated 91 GHz microwave and then fed real ~11 µm IR
(IRAR)**. The documented "~1.8σ sim→real BT cold bias" is a different physical quantity, not a
calibration offset, and it is a strong candidate for why BT never delivered intensity.

Evidence from I31 step 1 (`results_hafs/bt_dvorak_sim_p58` vs `_p64`, `scripts/bt_dvorak_diagnostic.py`):
Dvorak features trained on HAFS param 58 predict **real** best-track Vmax with skill 0.28 (RMSE 10.25 vs
climatology 14.17); the same features on param 64 give −0.01 (bias +4.6).

**Affected runs (audited from each run's recorded config, `scratchpad/bt_channel_audit.py`):** every
BT run recorded `bt_token_channel=6, bt_dense_channels=[6]` (param 64): `uobs_btir_tok`,
`uobs_btir_unet`, `uobs_btir_unet_24h`, `seqfm_propagation_btir_retry2`, `ftsar_btir_tok_0000`
(incl. the selected CFG 1.5 model), `ftsar_btir_tok_{intense_v1,radial,radial_lo}`,
`ftsar_btir_unet_0000`, `ftsar_btir_unet_24h_*` (4), `det_btir24h_*` (4),
`ft_det_btir24h_confirmation_001`. Eval dumps inherit the loaded run's channel. The real side
is affected too: `sar_finetune_datamodule` and the V04 eval z-score real IRAR IR with the
param-64 statistics (274 K / 17.6 K), because the default carries the wrong comment
`# 6 = ch 64, IR window`. Unaffected: no-BT models (`uobs_{base,scat,dir,rad,all}`,
`ftsar_all*`) and the student IR model (real IR only).

### P0b.1 — HANDOFF (another person): retrain the 24 h dense-BT chain on ABI band 13

**Owner: Codex, queued 2026-09-24.** Matched B13 and param-64 H1/H2 chains,
frozen-test and Anggrek scores are listed in the
[P0/P0b rerun ledger](details/p0_direction_b13_rerun.md).

Owner: **to assign** (handed off 2026-09-24; not taken by the neural-field work).
Use param 58 = **index 3** of `sat_stats.json` channels `[53,54,55,58,62,63,64,65]`
(B13 stats: mean 272.14 K, std 25.90 K). Keep index 6 available only as an explicit option; the
defaults must still reproduce old run.locks (so pass the channel in the new configs; don't just
change the datamodule default silently).

1. **H1, HAFS pretraining (can start now).** New config `cfg_unet_24h_b13` in
   `maxss_configs/train/direct_flow_hafs_btir.py` = deepcopy of `cfg_unet_24h` with
   `datamodule.bt_dense_channels=[3]`, `datamodule.bt_token_channel=3`, save_dir
   `results_hafs/uobs_btir_unet_24h_b13`. **Do not warm-start from `uobs_btir_unet`** (its BT
   input weights were learned on 91 GHz). Warm-start from the no-BT `uobs_all_0000` with
   `init_expand_input_channels=True` (new BT channels zero-initialised), or train fresh.
   The previous H1 (job 3258145) hit the 4.5-day wall; its selected checkpoint was epoch 39
   (val field RMSE 1.564), so plan a comparable budget and select on val.
2. **H2, real-SAR fine-tune (blocked by P0).** Analog of
   `sar_finetune.cfg_btir_unet_24h_hafspre_epoch39` with
   `RealSarFinetuneDataModule(bt_dense_channels=(3,), bt_token_channel=3)`, so real IRAR is
   z-scored with B13 statistics, initialised from the new H1 best checkpoint. It uses SAR u/v
   targets, so wait for the P0 direction fix. For attribution, also rerun the param-64 H2 with the
   fixed targets as the matched control; otherwise the channel and direction fixes are confounded.
3. **Eval:** frozen 526-acquisition test + Anggrek lifecycle through `benchmark.unified_recon`
   (the eval reads the BT channels and stats from the run config, so B13 propagates
   automatically; verify in the log line "dense BT channels [3]"). Report per band
   (`report_by_intensity.py`) with per-member Vmax, plus the vector/rotation-sense metrics from P0.
   **Key readout:** does B13 BT now move strong-band Vmax (the param-64 no-BT diagnostic moved
   Vmax MAE only 4.75 → 4.79)?
4. Re-measure the sim→real BT offset on B13 (`results_hafs/bt_dvorak_sim_p58`: simulated cloud
   tops ~25 K warmer in the extreme band) and decide whether a normalisation shift is needed.

- [ ] Later: the token (`btir_tok`) chain on B13 and the D-track warm starts (after P0b.1 reads out).
- [ ] Re-evaluate the "BT gives structure, not intensity" and "BT window irrelevant" (D1) conclusions:
      they were measured with the wrong channel.
- [ ] Optional: multi-channel BT (B13 + WV bands 8–10) in sim, since real WV exists on GOES/Himawari.

---

## I23 — Axisymmetric flow waypoint

**Status: first arm failed proxy promotion (2026-09-21); no confirmation run.** Accepted 2026-09-07. Promote
[I23](ideas.md#i23--flow-path-through-an-axisymmetric-intermediate-donut-marginal--promoted-2026-09-07)
to a simulated/full-field experiment. Hypothesis: explicitly learning a cylindrical
axisymmetric waypoint improves intensity/radial structure without worsening field
skill or calibration. First arm: `axisym_waypoint_tau05`, tau=0.5, no auxiliary.
Control: ordinary linear flow with matched architecture, initialization, data,
conditioning, seeds, optimizer-step budget and sampling cost.

- [x] Implement and verify cylindrical u/v projection and two-segment path primitives.
  Completed 2026-09-08 in `maxss_diff/axisymmetric_flow.py`: physical-coordinate
  projection, configurable ring width/exact-radius reference, centre handling,
  finite-field checks, and batched piecewise state/velocity targets. Synthetic
  Rankine tests cover both rotation signs, odd/even grids, radial flow,
  idempotence, gradients, translation removal, endpoints and velocity slopes.
  Verification: **36 passed** across `test_axisymmetric_flow.py` and existing
  `test_radial_losses.py`. Reproduce from `maxss-ml/` with
  `CONDA_OVERRIDE_CUDA=13.0 pixi run --frozen python -m pytest tests/test_axisymmetric_flow.py tests/test_radial_losses.py -q`.
  Training/sampling integration verified 2026-09-21 (see below).
- [x] Wire an opt-in training path (default remains linear); project in physical
  units, then normalize the waypoint. Reject partial/masked real-SAR targets.
  Audit clean-estimate auxiliaries: `x_t + (1-t)*v` is invalid on segment one.
- [x] Split sampling exactly at tau, with segment-correct endpoint velocities;
  expose/save the intermediate state and score against projected full-field truth.
  Verified 2026-09-21: **56 passed** across axisymmetric primitives, integration
  and radial-loss tests. The opt-in path rejects nonfinite/masked targets,
  incompatible clean-field auxiliaries and unadapted measurement guidance.
  Sampling preserves the control's Euler-call budget; validation saves physical
  waypoint/final tensors and logs waypoint u/v RMSE, speed RMSE and asymmetry.
  Actual HAFS CPU preflight passed on a finite `(2, 2, 64, 64)` validation batch:
  loss **1.237685**, finite backward and both sampled states. The parent checkpoint
  matches every learned weight; only the two newly introduced, inactive empty
  annular buffers need initialization. Reproduce with
  `CONDA_OVERRIDE_CUDA=13.0 pixi run --frozen python scripts/check_axisymmetric_flow.py`
  from `maxss-ml/`.
- [x] Register matched configs and run smoke, then proxy only after smoke passes.
  Configs are registered in `maxss_configs/index.md`. On 2026-09-21,
  waypoint smoke **4651934** (`axisym_waypoint_tau05_smoke`) completed all
  300 steps, exit 0. Training loss decreased **0.930 → 0.642**; validation
  waypoint u/v RMSE **7.880 → 7.555 m/s**, while final-field RMSE changed
  **3.782 → 3.883 m/s**. This is a finite learning-sanity pass, not a skill win.
  Its paired linear smoke **4659557** (`axisym_linear_control_smoke`) also
  completed all 300 steps, exit 0, in 5m23s (waypoint: 3m21s). Linear validation
  field RMSE improved **3.709 → 3.547 m/s** and final Vmax error was **5.850 m/s**,
  versus **6.502 m/s** for the waypoint. Both pass the execution/learning-sanity
  gate; the waypoint's final field RMSE is **9.5% worse** on this tiny panel.
  This smoke tier cannot establish scientific superiority or reject the hypothesis.
  Both use the original HAFS parent, seed 2300, the shared 64² smoke overlay,
  300 optimizer steps and 20 Euler calls per metric sample.
  Matched proxies submitted 2026-09-21: waypoint **4670412**
  (`axisym_waypoint_tau05_proxy`, completed in 1h33m44s) and linear **4670487**
  (`axisym_linear_control_proxy`, completed in 1h35m30s). Both exited 0 at
  10,000 steps and use `hafs_proxy.yaml`:
  128², batch 32, 10,000 optimizer steps, two fixed metric batches, seed 2300,
  and the same original `uobs_btir_tok` initialization (not smoke checkpoints).
  Submitted with `slurm_gpu_hpc.yaml`. Final field RMSE / Vmax MAE:
  waypoint **3.669 / 7.104 m/s**, linear **2.294 / 2.368 m/s**.
  Waypoint is worse on both metrics at all 20 matched validation checkpoints.
  Its best logged field RMSE is **3.127** at step 500, versus linear **2.294**
  at step 10,000. Waypoint u/v RMSE improves **6.010 → 2.061 m/s** and
  asymmetry RMS **3.351 → 0.081 m/s**, but final reconstruction degrades.
  **Do not promote this arm or launch the conditional tau/auxiliary sweep.**
  This is a 16-case, single-sample proxy panel, not a frozen-test ensemble result;
  CRPS, calibration, radius metrics and intensity strata have not been scored.
  `results.json` fields named `best_val_*` actually contain final values;
  use `metrics.csv` for logged minima. Full result is recorded in
  [the results log](details/unified_reconstruction_results.md#i23--axisymmetric-waypoint-proxy-2026-09-21).
- [ ] Compare field RMSE/CRPS, Vmax bias/MAE, radial-profile error, RMW,
  R34 and ensemble calibration on common cases and intensity strata. Promotion
  requires better intensity/profile skill without field/calibration degradation.
- [ ] If the first arm passes, test tau=0.3/0.7, waypoint supervision on/off,
  centre perturbations and the wavenumber-0–1 alternative as separate hypotheses.

Discretization caveat: finite-width cylindrical rings smooth radial structure;
exact-radius rings preserve synthetic Rankine vortices but have sparse angular
coverage. Validate both, including centre convention and outer incomplete rings.
An axisymmetric projection need not preserve the full asymmetric field's Vmax.
The exact pure-axisymmetric bottleneck also removes state-carried asymmetry;
assess diversity after tau explicitly before interpreting it as a useful prior.

---

## E — Evaluation (V04 real obs)

**Status: complete.** All four V04 real dumps are scored on the 104-acquisition
val-2022 OSE set; results are in the scoreboard and in
[unified_reconstruction_results.md](details/unified_reconstruction_results.md).
Best real RMSE is **2.93** (`btir_tok`, all obs + BT), against ≈5.2 for the best
V03 baseline. Real scatterometer direction fixes `dir`'s sim→real collapse
(7.56→4.91), and BT tokens help despite the cold bias (3.53→2.93).

**Decision:** `btir_tok_real_v04` is the preferred BT model. Dense BT has a similar
signed Vmax error but is worse on RMSE, CRPS, profile MAE, Vmax MAE and RMW MAE.
This V04 evaluation is what selected the Phase-C parent in section F.

**Next:**
- **P3.2 measurement-guidance ceiling** on the dir/all/btir checkpoints — the one
  item still open in this track. Before re-running, apply
  [ideas.md](ideas.md) I19: every guided run so far used `n_steps=50`, identical to
  unguided, whereas NVIDIA's score-based DA uses ~96. An under-resolved solver is an
  untested explanation for our consistently modest guidance gains, and a
  50/96/150 step sweep on one configuration is inference-only.

**Dropped:** the failed `uobs_all` V03 `all_real` re-submission (job 2589804). V03
carries speed only and is fully superseded by `all_real_v04`; re-running it would
add a baseline nothing is compared against.

Code: `maxss_data/obs_v04.py` (V04Store: direction + BT tokens/dense), `infer_unified_recon`
`use_v04`. Launch: `flexlock-run -d maxss_configs.benchmark.unified_recon.cfg -s main -o
run_dir=results_hafs/uobs_<slug>_0000 main.mode=real main.use_v04=True main.save_dir=... --slurm-config maxss-ml/slurm_gpu_hpc.yaml`.

---

## F — Real-SAR fine-tuning (Phase C)

**Status: model selected, evaluation essentially complete.** Nine Phase-C variants
were trained and all are scored on the frozen 526-acquisition test; the selected
model is `ftsar_btir_tok` sampled at **CFG 1.5**. Both HTML reports and the
scoreboard are current. What remains is one decision, one cheap statistical gap, and
the open scientific problem below. Plan:
[phase_c_sar_finetune_plan.md](tracks/phase_c_sar_finetune_plan.md); full result
tables in [unified_reconstruction_results.md](details/unified_reconstruction_results.md)
and `tcwind_benchtools/results/scoreboard/scoreboard.md`. Training history and job
forensics are in [done.md](done.md).

**Design (resolved):** fine-tune `uobs_all_0000` on **real data with real SAR as target**.
Objective = **real u,v target** built from SAR speed × SAR `wind_dir` (both in V04,
~99% co-located), standard FM velocity loss **masked to the in-swath pixels**; out-of-swath
unsupervised. Low LR (1e-5–5e-5), EMA on, keep p_null/dropout for CFG.

**Split (done):** `maxss_data/splits/ft_sar_v1.json` (config `uobs_splits.cfg_ft`):
train 471 storms / 2206 SAR, val 39 (2022), **test 66 = 2023 + anggrek (`sh062024`)**.

**Results (frozen 526-acquisition test, `ft_sar_v1` test = 2023 + Anggrek).**
Full ten-row table in `scoreboard.md`; the ordering that matters:

| model | field RMSE | CRPS | Vmax MAE | strong-storm Vmax MAE |
|---|---:|---:|---:|---:|
| `ftsar_btir_tok` @ **CFG 1.5** — **selected** | **2.46** | **1.16** | **4.73** | 11.81 |
| `ftsar_btir_tok` @ CFG 1 | 2.62 | 1.25 | 5.31 | 13.62 |
| `ftsar_btir_unet_24h_hafspre_epoch39` | 2.68 | 1.31 | 4.75 | 12.12 |
| `ftsar_all` (Phase-C baseline) | 2.69 | 1.32 | 5.33 | 12.61 |
| `ftsar_all_vmax_ramp` | 2.70 | 1.34 | 5.26 | **9.46** |
| `uobs_btir_tok` (warm start, no Phase C) | 3.11 | 1.56 | 7.41 | — |
| `uobs_btir_unet_24h_epoch39` (warm start) | 3.21 | 1.70 | 6.26 | — |

Phase-C fine-tuning is worth −21% RMSE on the token-BT branch (3.11→2.46) and −16%
on the dense-BT branch (3.21→2.68). CFG 1.5 leads every headline metric at once and
wins field RMSE in all three intensity bands.

**Anggrek lifecycle (171 frames, 3-hourly, vs IBTrACS).** The selected model gives
Vmax RMSE/bias/MAE **12.639/-6.174/8.639** m/s (162 pairs) and R34 mean
RMSE/bias/MAE **41.075/-23.883/30.945** km (132 pairs) — the **best storm size of any
variant** (previous best MAE 35.865) but well behind `ftsar_all_vmax_ramp` on Vmax
(7.924). Both HTML reports were refreshed on 2026-09-04 and include this run.

**Our BT representation delivers structure, not intensity.** The paired 526-case no-BT
diagnostic (job 3647817) worsens RMSE 2.675→2.755, CRPS 1.315→1.359 and profile MAE
2.071→2.186, while Vmax MAE barely moves (4.748→4.793; 12.12→12.77 for strong
storms). *Corrected reading (2026-09-24, user):* this says our current use of BT does not
extract intensity. It does **not** say BT lacks intensity information: IR is the main input
to operational intensity estimation (Dvorak). See [ideas.md I31](ideas.md).

**IBTrACS reference trap (fixed 2026-09-04).** Two files share the basename
`IBTrACS.since1980.v04r01.nc`: `tcwind_benchtools/data/` (what every frozen score and
both reports use) and the project-root `data/` copy from 2025-10. They disagree on
107 of 153 overlapping Anggrek Vmax values by up to 7.7 m/s. `score_dump_ibtracs.py`
defaulted to the wrong one. Fixed to resolve absolutely; never pass
`--ibtracs ../data/...`. Verify a suspect score by reproducing
`ftsar_all_vmax_ramp_lifecycle_3h` = Vmax RMSE 7.923967 / 162 pairs.

**Next:**

1. **Resolve the field-versus-intensity trade-off — the one open scientific problem.**
   Nothing reconstructs the field and the peak intensity at once. CFG 1.5 wins field
   RMSE, CRPS, profile MAE and storm size; `ftsar_all_vmax_ramp` wins strong-storm
   Vmax (9.46 vs 11.81 MAE) and lifecycle Vmax (7.92 vs 12.64 RMSE), and each loses
   the other. Both signals are consistent across the frozen test *and* the Anggrek
   lifecycle, so this is a property of the models, not of one evaluation. Design the
   next experiment against this trade-off directly; do **not** launch further
   single-metric weight sweeps, which is what produced the current stalemate.
   Diagnostic candidates already written up: [ideas.md](ideas.md) I13
   (Vmax-ramp morphology/artifact audit — is the ramp's intensity real or
   fragmented high-wind speckle?) and I17 (log spectral distance — is CFG 1.5's field
   advantage genuine sharpness or favourable smoothing?). Those two together should
   determine whether the trade-off is fundamental or an artifact of how each variant
   cheats its own metric.

2. **Storm-bootstrap confidence intervals on the frozen-test comparisons.** D1 field
   scoring is complete for all nine variants, but every ranking in the table above is
   a point estimate. Several gaps we are treating as real are small — 2.68 vs 2.69 vs
   2.70 across three different models — and may not survive resampling over the 66
   test storms. Cheap (`per_sample.csv` already holds everything needed) and it
   decides how many of the current "conclusions" are actually conclusions. Pair with
   the fair-CRPS correction in [ideas.md](ideas.md) I15: at M=8 the biased CRPS
   estimator is off by ~14% in its spread term, the same order as the CRPS gaps being
   ranked.

3. ~~Auxiliary-checkpoint evaluations~~ — **dropped 2026-09-05 by decision.**
   `ftsar_btir_unet_24h_singleworker` (val 3.9453), annular-only (3.8523) and
   annular+profile (4.1071) all lose to the Phase-C baseline (3.7766) on validation
   and will not be scored on the frozen test. Their checkpoints remain on disk; the
   only blocker to reviving one was a `run_dir` missing the `maxss-ml/` prefix.
   Reopen only if item 1 identifies annular structure as the mechanism — note that
   the annular-norm and profile losses reappear as ablation axes in the Phase-D plan
   below, so they will be tested there in a controlled setting instead.

### Trade-off evidence gathered 2026-09-05 (before choosing an experiment)

**ERA5 guidance (ideas.md I14) will not help the trade-off — do not run it first.**
The data prerequisite is met: `ref_data/V04/era5/` is fully compiled, 1204 storms,
with exactly the 171 Anggrek frames as `wind_speed`/`wind_dir` on the same
storm-centred grid as every other source, so the loader work is small. The problem is
scientific, not engineering. Scored against IBTrACS over the Anggrek lifecycle, ERA5
itself gives **Vmax RMSE 18.14, bias -13.68, MAE 13.70** (162 pairs) and R34
RMSE/bias/MAE **56.40/-42.90/45.38** km (132 pairs) — worse on both axes than every
model we have, including the worst. **ERA5 peaks at 23.1 m/s over a lifecycle where
IBTrACS peaks at 59.2 m/s**: it never reaches Cat 1 for a storm that reached Cat 4.
I14's one-sided design is careful (above 15 m/s it only applies a speed *lower*
bound, so it cannot drag the core down), but that means the constraint is **inert
exactly where our problem is** — it can only act on the outer field, where CFG 1.5 is
already the best variant on record for R34. Keep I14 as a possible outer-field /
environment refinement, not as an intensity lever.

**Grid resolution is *not* the explanation for our Vmax under-bias — ruled out.**
Our dumps are 128² at 6 km; the reference student product is 171² at 3 km, so the
obvious worry was that we simply cannot resolve an eyewall peak. Block-averaging the
student's 3 km field to our 6 km grid over all 192 frames costs only **0.22 m/s of
Vmax on average and 0.80 m/s over the 20 strongest frames** — an order of magnitude
below our -6.17 m/s bias. Our under-bias is a genuine model property. (Caveat: the
student field is itself a 24-hour temporal mean and therefore smooth, so 0.80 m/s is
a lower bound on the penalty a sharper field would pay; it is not within an order of
magnitude of closing the gap either way.)

**The student model sits at the opposite corner of the same trade-off.** On the
common Anggrek report it scores Vmax RMSE/bias/MAE **5.44/-0.17/3.72** — an
essentially unbiased peak intensity, better than our best (`ftsar_all_vmax_ramp`,
7.92) — while its R34 bias/MAE is **+65.03/+65.03 km** against our best of 30.95. Our
models are biased *low* on both Vmax and R34; it is unbiased on Vmax and far too
broad on size. Whatever it does to get peak intensity right is the thing we do not
have, which is the strongest available argument for the Phase-D reproduction below.
The comparison is currently only indicative — different cadence (2 h vs 3 h),
resolution (3 km vs 6 km) and pair counts (192/178 vs 162/132), as the report's own
comparability note says. Making it controlled is the point of Phase D.

**SUPERSEDED 2026-09-06 — `ftsar_all_vmax_ramp`'s intensity advantage was a
diagnostic artifact.** Its lifecycle Vmax was scored from the ensemble-MEAN field,
which averaging biases low by ~8 m/s on Anggrek. That penalty hits 8-member ensembles
and not single-member deterministic dumps, so the old table compared a smoothed
statistic with an unsmoothed one. On the mean of per-member maxima — the statistic
this project already recommended for intensity — `ftsar_all_vmax_ramp` scores Vmax
RMSE **13.22** and bias **+9.86**, second worst of ten lifecycles, versus the 7.92 /
-4.25 that earned it the "intensity candidate" label. Its members are individually far
too strong and averaging flattered them. `score_dump_ibtracs.py` now emits
`vmax_mbr_*_ms` and `n_members` alongside the originals (which keep their meaning so
historical scores stay reproducible), and every lifecycle has been re-scored. Full
corrected table:
[unified_reconstruction_results.md](details/unified_reconstruction_results.md).
**Anything downstream that called this model the intensity candidate — the mid-term
report, the Anggrek report, the frozen-test narrative — needs revisiting.**

**Original entry (numbers no longer support the conclusion):** Its predefined high-intensity diagnostic is complete (frozen
test job 3578118, salvaged and scored by 3596954). Overall it is slightly worse than
the Phase-C baseline (RMSE 2.698 vs 2.690, CRPS 1.336 vs 1.322, Rmax MAE 46.8 vs
43.4) and better on Vmax (5.26 vs 5.33) and profile MAE (2.079 vs 2.108). On the 36
strong cases it is clearly better (field RMSE 4.05 vs 4.21, Vmax MAE 9.46 vs 12.61)
and its signed Vmax error is near zero (-0.31 overall). That is a genuine
strong-storm win bought with a small aggregate loss — keep it as the intensity arm of
item 1, and do not select between it and CFG 1.5 until item 1 resolves.

---

## D — IR→wind reproduction and the intensity mechanism (Phase D)

**Hypothesis.** The student IR→wind model achieves an essentially unbiased Anggrek
Vmax (bias -0.17 m/s vs our best -4.25) while being far too broad in size (R34 bias
+65.0 km vs our -6.9). It therefore holds the half of the trade-off we lack. Reproduce
its training **on real data inside our bench and under FlexLock**, confirm the low
Vmax bias reproduces, and then ablate to isolate *which ingredient* produces it.

**Why this and not more variants of ours:** every model we have is biased low on both
Vmax and R34, so no internal ablation has ever shown us an unbiased-intensity
reference. This imports one. It also converts an indicative comparison into a
controlled one — the current student numbers come from a different cadence (2 h vs
3 h), resolution (3 km vs 6 km) and pair count (192/178 vs 162/132), so the report's
comparability note applies and no clean attribution is possible today.

**Source.** `src/IR_to_SAR/` inside the student repo, which since 2026-09-07 is
readable at `/scale/project/ifremer-isi-jumeaunumerique/alternance_tannaoui/alternance`
(regression U-Net, flow matching, residual FM). `ML_IR_SAR/config.py` already exposes every ablation axis as a config
field, which maps cleanly onto `py2cfg`: `irwin_channels`/`in_channels` (temporal
window), `norm` (annular normalization; implementation in
`callbacks_functions.py:annular_denormalization`), `w_pix`/`w_grad`/`w_radial`
(profile/radial loss, via `combined_sar_loss` and `temporal_combined_sar_loss`),
plus `add_era5`, `use_flow_matching`, `use_residu`, `channel_dropout`. Candidate
loss/normalization details were already triaged in [ideas.md](ideas.md) I7, including
two corrections to make before adopting anything.

**Stage D0 — BUILT and smoke-passed 2026-09-05.** Losses in
`maxss_diff/radial_losses.py` (14 unit tests), wired into
`DeterministicReconstructionLightningModule` behind `w_radial`/`w_grad`, both
defaulting to 0.0 so existing run.locks reproduce exactly. Configs in
`maxss_configs/train/ir_regression.py`, registered in `index.md`; every variant is a
named delta from `deterministic_btir.cfg_phase_c` (slug `ft_det_btir24h`, the matched
baseline that scored Anggrek Vmax bias -10.11), so differences are attributable.
Smoke `irreg_smoke` reached `run.complete` with finite auxiliaries and the weighting
verified exactly (`4.9567 + 1.0*2.2478 + 0.5*0.0968 = 7.2529`).

Two findings from the build worth keeping:
- **The IFREMER data pipeline is unusable directly.** Its prepared sequences were under
  `/scale/user/mtannaou/alternance/.../csv_data/` — permission denied. D0 therefore
  rebuilds from V04, which is what our split requires anyway.
  *(Access resolved 2026-09-07 — the pickles are readable at the new path above. The
  decision stands regardless: we need our own split, not theirs. But the files are now
  available for introspection, which is what unblocked D2.)*
- **Their split is not comparable.** `PrepareDataSet` hardcodes the split by year and
  selects `year in [2018]` for *both* validation and test, so the two sets are
  identical. Their published numbers are not a clean reproduction target; we train on
  `ft_sar_v1` and compare only through our own harness.

**Known gap in the reproduction:** the student predicts a 12-frame sequence and
publishes the 24-hour temporal mean of deltas; this architecture predicts a single
field. That aggregation is the prime suspect for *both* the unbiased Vmax and the
+65 km R34, and it needs a multi-frame output head — a separate build. Run the cheap
variants first: they either account for the gap or exclude the loss ingredients and
leave temporal aggregation as the answer. Note `ft_det_btir24h` is already a
deterministic 24-hour-BT model at Vmax bias -10.11, so the mechanism is *not*
"deterministic + 24 h BT".

**D0 RESULT (2026-09-06): the radial-profile loss halves the Vmax bias and costs
nothing.** Jobs 3680068 (`irreg_radial`) and 3680069 (`irreg_repro`) trained 60
epochs; both were dumped on the frozen test and the 171-frame Anggrek lifecycle and
scored by the standard harness. All three deterministic rows share architecture,
warm start, split and budget, so differences are attributable.

Frozen test (526 acquisitions, single member):

| model | RMSE | profMAE | Vmax err | Vmax MAE | Rmax MAE |
|---|---:|---:|---:|---:|---:|
| `ft_det_btir24h` (baseline) | 3.222 | 2.300 | -3.90 | 5.63 | 44.9 |
| **`irreg_radial`** (+ radial loss) | **3.181** | **2.184** | **-2.39** | **4.84** | **42.0** |
| `irreg_repro` (IR-only + radial + grad) | 4.608 | 3.247 | -4.01 | 6.35 | 45.1 |

Anggrek lifecycle vs IBTrACS (162 Vmax / 132 R34 pairs):

| model | Vmax RMSE | Vmax bias | Vmax MAE | R34 MAE |
|---|---:|---:|---:|---:|
| `ft_det_btir24h` (baseline) | 12.072 | -10.110 | 10.110 | 56.82 |
| **`irreg_radial`** | **7.579** | **-5.266** | **5.905** | **48.61** |
| `irreg_repro` | **6.775** | **-3.500** | **5.630** | 60.78 |
| `ftsar_all_vmax_ramp` (best prior, any family) | 7.924 | -4.255 | 5.990 | 35.87 |
| student (target) | 5.440 | -0.167 | 3.724 | 65.03 |

**No trade-off.** `irreg_radial` improves *every* headline metric over its matched
baseline on *both* products — field RMSE, profile MAE, Vmax error, Vmax MAE, Rmax
MAE, and lifecycle R34 MAE. This is the first change in the project that buys
intensity without paying for it in field skill, and it contrasts directly with the
`vmax_ramp` auxiliary, which bought Vmax by degrading field error. The mechanistic
reason is in `radial_losses.py`: supervising the maximum *per radius bin* constrains
the whole vortex profile, where the earlier global p-norm Vmax auxiliary could be
satisfied by one bright pixel.

**The gate was not met, and that is informative.** D0 required a Vmax bias within
about ±1.5 of the student's -0.17. The best achieved is -3.50. The loss ingredients
account for roughly two-thirds of the gap (-10.11 → -3.50) but not the remainder,
which is consistent with the un-reproduced piece: the student's 12-frame output plus
24-hour temporal mean of deltas.
*(Superseded framing — see D1 below: that -0.17 target is band cancellation, so the
gate was mis-specified. The two-thirds statement about the loss ingredients stands;
the ±1.5-of--0.17 criterion does not, and has been replaced by per-band bias.)*

**IR-only flips ranking between the two products, which explains the student's
profile.** `irreg_repro` is much worse on the frozen test (4.61 vs 3.18) yet better
on lifecycle Vmax (6.78 vs 7.58). Frozen-test cases are SAR acquisition *times*,
where observation tokens carry most of the signal, so removing them hurts badly; over
a full lifecycle most frames have no overpass and that advantage disappears. It also
matches the student's own signature — good lifecycle intensity, poor storm size
(its R34 bias +65.0; `irreg_repro`'s R34 MAE 60.8 is likewise its weakest metric).

**D1 RESULT (2026-09-07): the BT temporal window is nearly irrelevant.**
`cfg_w12` (12 frames, 24 h @ 2 h, `in_channels` 24) and `cfg_w1` (1 frame, no
history, `in_channels` 2) bracket the 8-frame `irreg_radial`. All three share loss,
architecture, warm start, split and budget, so the window is the only variable.

Frozen test (526 acq) / Anggrek lifecycle aggregate:

| model | frames | RMSE | profMAE | Vmax err | Rmax MAE | life Vmax bias | wall |
|---|--:|---:|---:|---:|---:|---:|---|
| `irreg_radial` | 8 | 3.181 | 2.184 | -2.39 | 42.0 | -5.27 | 3h43 |
| `irreg_w12` | 12 | 3.201 | **2.177** | **-2.20** | 41.4 | **-4.46** | 3h43 |
| `irreg_w1` | **1** | **3.152** | 2.169 | -2.41 | **40.5** | -5.34 | **1h41** |

A model that sees **one BT frame and no history at all** matches the 8-frame model
everywhere: better on frozen-test field RMSE and Rmax MAE, identical on Vmax MAE,
within 0.3 m/s on the lifecycle. Per band the three arms are within noise in weak
and moderate on both products. The 1/8/12 spread is smaller than the gap the radial
loss opened on its own.

The one place the window shows up runs *opposite* to the hypothesis: in the frozen
test's strong band, fewer frames is monotonically better — Vmax err -7.95 (8 fr) →
-7.17 (12 fr) → **-7.00** (1 fr), Rmax MAE 41.0 → 38.6 → **32.9**. History is not
helping intense storms, it is smearing them. n=36, so directional.

**This closes the temporal-window hypothesis.** The remaining gap to the student
cannot be attributed to how much history the model *ingests*. What was never
reproduced is the 12-frame **output** head and the 24 h temporal mean of deltas —
an averaging operation over *predictions*, not over inputs, and now the only
structural difference left on the list. *(D2 below splits this into two separable
halves and shows the averaging half needs no new architecture.)*

**The D0 gate was itself measuring the wrong thing.** Stratified by intensity, the
student's headline Anggrek Vmax bias of -0.17 m/s is **cancellation, not accuracy**:
+1.86 weak (n=139), -4.98 moderate (n=45), -8.40 strong (n=8) — which reproduces
-0.167 exactly on its own pair counts. It is the only model in the comparison that
*over*-predicts weak storms, and it still under-predicts Cat 4–5 by 8.4 m/s. A gate
of "match -0.17" therefore rewards reproducing the cancellation. **Per-band bias is
the target.** On moderate-band Vmax bias, `irreg_w12` at -8.25 is our best
deterministic arm against the student's -4.98.

Second band-level correction: `irreg_radial`'s aggregate "no metric regresses" is
true only in aggregate. Strong-band field skill does regress (RMSE 4.282→4.494,
profMAE 2.683→2.902), so the auxiliary buys strong-storm intensity with a little
field error there and nowhere else. `scoreboard.md` has been corrected.

Third: `irreg_repro` (IR-only) beats the student in the strong band on Vmax
(bias -6.19 vs -8.40) and pays with R34 MAE of 136.6 km — a vortex nearly three
times too broad. That is the student's own signature amplified, and it supports
reading the +65 km R34 and the intensity stability as **one mechanism, not two**.

**Ports and side results:**
- The flow-family port of the radial loss (`ftsar_btir_tok_radial{,_lo}`) did **not**
  transfer — see [details/unified_reconstruction_results.md](details/unified_reconstruction_results.md).
  The deterministic family started at -10.11 bias so the push corrected it; the flow
  members were already near-unbiased per member, so the same push overshoots to
  +5.6/+7.2 on the lifecycle. It does win the *moderate* band on both products
  (frozen-test Vmax MAE 6.91 vs 7.30; lifecycle 10.62 vs 12.24) while badly
  over-strengthening weak storms. The auxiliary applies a roughly intensity-uniform
  push, so it helps where the deficit matches its magnitude and hurts where there is
  none. An intensity-gated ramp on the radial target is the cheap variant if this is
  revisited.
- `irreg_w1` trains in **1h41 vs 3h43** and evaluates faster at no cost in skill —
  use it as the iteration vehicle for further deterministic loss experiments.

**Still unrun** (deliberately parked, not blocked): `cfg_grad` (isolates the gradient
loss from the radial loss) and `cfg_ironly` (isolates dropping observation tokens
from the loss change). Neither bears on the output-head question.

**D2 (2026-09-07): the mechanism is now read from the source, and it is not what we
assumed.** The student repo became readable at
`/scale/project/ifremer-isi-jumeaunumerique/alternance_tannaoui/alternance` — the full
working tree, including the exact checkpoint behind the lifecycle CSV we score. From
`config_fallback.txt`, `data_preparation/prepare_dataset.py` and
`best_result_so_far/temporale_mode/inference_v1.ipynb`, the "12-frame output head +
24 h temporal mean of deltas" decomposes into **two separable halves**, which their
setup confounds and ours must not:

1. **Training-time (the head).** A window is 12 frames at a **2 h** step (22 h span);
   windows slide by one frame. The net is `UNet2DModel` 12→12. Each window contains
   exactly one SAR overpass and the loss masks every channel without SAR, so each
   overpass enters training **12 times, once per output-channel position** — the model
   must predict the SAR field at any lag from -12 h to +10 h. The two temporal
   regularizers are inert (`lambda_neighbors=1e-5`, `lambda_stability=1e-10`), so
   there is no temporal-smoothness term doing hidden work.
2. **Inference-time (the mean).** Each target time is covered by 12 overlapping
   windows, giving 12 estimates at 12 different lags; the published field is their
   **plain mean**.

So the "temporal mean" is a **test-time ensemble over shifted input windows**, not a
training construct — and half 2 needs **no new architecture at all**. That reorders
the plan: the averaging is testable on checkpoints we already have.

Two further facts from the source, both material:
- **Their `w_radial` is 2.0; ours is 1.0.** Radial weight is the one lever that has
  moved Vmax for us, so a reproduction that holds it at our value is not a
  reproduction. Sweep it.
- **The split bug is worse than recorded above.** `val == test == 2018` (the `elif`
  branch is unreachable), so selection ran on the test set — final radial loss 0.33
  train vs 0.80 val over 110 epochs. And *everything else* is training data, 2017 and
  2019–2024. **Our frozen 526-acquisition test is 2023, inside their training set: the
  student can never be scored there.** We have only ever compared on the lifecycle, so
  nothing is retracted. Anggrek `sh062024` is *not* in their training windows
  (verified against the 7982-window index), so the lifecycle comparison is clean.

**D3 RESULT (2026-09-07): temporal averaging is not the mechanism — it moves both
metrics the wrong way.** New tool
`tcwind_benchtools/scripts/temporal_average_dump.py` replaces each field in a
lifecycle dump by a centred moving average of its temporal neighbours and re-scores
through `score_dump_ibtracs.py`. No training, no model inference: the dumped fields
carry `centered: 1`, so averaging across timesteps *is* an average in the storm
frame, the same frame the student averages in.

*Read the design caveat before quoting these numbers.* This is not an exact
reproduction. The student's 12 estimates are all predictions **of** time t from
windows that place t at 12 different output-channel positions; ours are predictions
of the neighbouring times t±Δ. So this conflates averaging with genuine storm
evolution across the window, which should **overstate** the smoothing. It is an
upper bound on how much of the student's signature averaging can explain — which is
exactly what is needed to *exclude* it, and excluding is what happened.

Anggrek lifecycle, aggregate, window sweep at 3 h cadence:

| dump | Vmax bias | Vmax MAE | R34 bias | R34 MAE |
|---|---:|---:|---:|---:|
| `irreg_w1` (raw) | **-5.34** | **6.02** | **-22.6** | 51.8 |
| `irreg_w1_tavg6` | -6.70 | 6.71 | -30.7 | **50.5** |
| `irreg_w1_tavg12` | -6.94 | 6.94 | -33.2 | 51.1 |
| `irreg_w1_tavg22` | -7.08 | 7.08 | -34.3 | 51.6 |
| `irreg_radial` (raw) | **-5.27** | **5.90** | **-22.2** | 48.6 |
| `irreg_radial_tavg22` | -6.87 | 6.87 | -32.3 | **48.2** |

Monotonic in window length and reproduced on both arms. Averaging makes Vmax
**more** under-biased and the vortex **narrower**. The student's signature is the
opposite on both axes: weak-band Vmax bias **+1.86** and R34 bias **+65 km**. So the
averaging half cannot be what produces it, and the 22 h span — their actual span —
is the worst point of the sweep, not a sweet spot.

Per band the trade is sharper and more interesting than the aggregate:

| band | Vmax bias raw → tavg22 | R34 MAE raw → tavg22 |
|---|---:|---:|
| weak (n=120) | -3.82 → -4.93 | 56.4 → 62.4 |
| moderate (n=37) | -9.42 → -12.63 | 40.0 → **28.8** |
| strong (n=5) | -11.66 → -17.59 | 54.5 → **26.5** |

Averaging buys **size** accuracy in the moderate and strong bands and pays for it in
intensity — strong-band R34 MAE halves, 54.5 → 26.5 km. That is the reverse of the
student's trade (good intensity, bad size), which reinforces the exclusion. It is
also a free post-processing win on storm size for intense storms if we ever want one,
though n=5 makes it directional only. Weak-band Vmax *RMSE* improves slightly
(5.66 → 5.34) while bias worsens, i.e. it is smoothing noise, not adding skill.

**Where this leaves the track.** Both halves of the "12-frame output + 24 h temporal
mean" explanation are now excluded or demoted: input-history length by D1, output
averaging by D3. The untested differences that remain are in the **loss**, not the
architecture — which reorders D4 and D5.

**D5 first (cheap, one run): `w_radial` at 2.0.** Their value; ours is 1.0. Radial
weight is the only lever that has ever moved Vmax for us, and it is now the only
untested difference in their loss configuration. Run on `cfg_w1` (1h41). If the
mechanism is loss weighting, this is where it shows up.

**D4 last, and only if D5 fails: multi-frame output head.** Predict N frames with
per-channel masked supervision (half 1 above). D3 removed the reason to expect the
*averaging* to matter, but the head also acts as heavy augmentation — each overpass
seen at 12 lags — so it is not fully excluded. It is now the expensive tail of the
track, not its next step.

Read every result by intensity band (`tcwind_benchtools/scripts/report_by_intensity.py`),
never in aggregate.

*Primary readouts:* per-band Vmax bias and strong-storm Vmax MAE (the thing we want),
R34 bias/MAE (the thing the student gets wrong), and field RMSE/CRPS as the guard
rail — report all three together, exactly as the temporal track's failure taught us
([archive/temporal_sequence_fm.md](archive/temporal_sequence_fm.md)): a variant that
wins intensity while degrading the field is not a win.

**Not on the path:** ERA5 guidance (see the evidence in section F), further
single-metric weight sweeps on our own models, longer or denser BT input history
(excluded by D1), temporal averaging of the output as an *intensity* lever (excluded
by D3 — it is a size lever, and it costs intensity), and any gate phrased against the
student's *aggregate* Vmax bias.

---

## B — BTIR (geostationary BT) follow-up

**Status:** real BT eval is scored for both variants: token BT RMSE 2.93 versus
dense BT U-Net RMSE 3.63. Keep the tokenized variant.
Documented a **~1.8σ sim→real BT cold bias** (synthetic CRTM ch64 warmer than real TC-IRAR).

**Resolved 2026-09-05 — option (b) was already implemented and already won.** The
decision was framed as (a) distribution-match real BT to the training z-shape,
(b) fold real IRAR BT into Phase C fine-tuning, or (c) accept as-is. Option (b) is
what `cfg_btir_tok` already does: it fine-tunes through `RealSarFinetuneDataModule`
with `use_btir_tokens=True`, and that datamodule reads `bt_patch_*` from
`V04Store` — real IRAR, not synthetic CRTM
(`maxss_data/sar_finetune_datamodule.py:40,74`). The measured effect is the gap
between the sim-BT-trained `btir_tok_real_v04` (real RMSE 2.93) and the real-BT
fine-tune at CFG 1.5 (frozen-test RMSE 2.46). Fine-tuning absorbed the ~1.8σ cold
bias; no distribution-matching step is needed.

**Next:** none. Track closed. The residual BT question is not the bias but its
*contribution*: the paired no-BT diagnostic (job 3647817) showed BT improves field
structure (RMSE 2.675→2.755 without it) while barely moving peak intensity
(Vmax MAE 4.748→4.793). ~~BT is a structure cue, not an intensity cue~~ — corrected
2026-09-24: our tokens (96-km patch means that average the warm eye into the cold ring)
and dense conditioning fail to exploit BT's intensity signal (Dvorak). Reopened as
[ideas.md I31](ideas.md) (BT as a neural-field output head).

## Intensity-balanced training and NextGEMS expansion (2026-09-23)

User accepted the direction after I23 proxy evaluation. Work from the linear-flow
baseline. Detailed rationale, augmentation audit, commands and gates:
[Intensity-balanced training plan](details/intensity_balanced_training_plan.md).

- [x] Document balanced HAFS control, NextGEMS mixtures and augmentation scope.
- [x] Implement opt-in inventory-based band → storm → forecast-frame balancing;
  preserve default loaders and natural validation; regenerate pseudo-observations.
- [x] Add streaming physical/grid-Vmax inventory builder and focused sampling tests.
- [ ] Complete full inventory, inspect extreme weights and run real-loader smoke.
- [ ] Run matched natural/balanced proxy; evaluate high intensity and overall skill.
- [ ] Audit physical vector/metadata transforms before adding quarter-turn rotations.
- [ ] Inventory NextGEMS independent intense storms and implement compatible adapter.

## Background-aware generation (I27; 2026-09-23)

User proposed ERA5/first-guess starts and reverse ODE to improve fields outside
measurement swaths. [I27 in ideas](ideas.md#i27--background-aware-flow-initialization-and-outside-swath-guidance--proposed-2026-09-23)
records the testable sequence and evaluation controls.

- [ ] Inventory collocated ERA5/first-guess vector winds, time and resolution.
- [ ] Implement opt-in low-frequency background guidance in physical u/v.
- [ ] Compare background-guided sampling with noisy-midpoint starts and reverse
  ODE inversion on identical held-out cases; audit diversity and inner-core bias.

**2026-09-24 steering:** user chose a 10,000-frame intense-epoch recipe plus
rotation/small smooth Gaussian wind perturbations, and asked to try ERA5-start
inference. The natural HAFS control completed (Slurm 4820743, 10,000 steps).
The intense-epoch loader and opt-in linear-flow midpoint sampler are implemented;
see the linked plans and configs. The stochastic-replication arm remains an
unsubmitted ablation.

---

## V — Vmax conditioning adherence audit (2026-09-24)

**Why.** Real/lifecycle inference feeds best-track Vmax as the ATCF token and FiLM
(`infer_unified_recon.py:179`), so the lifecycle Vmax under-bias (−6.2 m/s selected
model; −8 to −12 m/s strong band) is produced *while the model is given the answer*.
Separate three explanations before any further intensity experiment: (a) a definitional
gap learned from HAFS truth, (b) weak adherence to the Vmax token, (c) genuine
structural failure. Also fixes the reading of the intensity-balanced run's gate.

- [x] **(a) HAFS truth grid Vmax vs HAFS ATCF Vmax.** Done 2026-09-24; full result in
  [done.md](done.md#vmax-adherence-audit-a-hafs-grid-vmax-vs-its-own-atcf-vmax-2026-09-24).
  Strong-band (≥58 m/s) 6 km grid Vmax is **−5.4 m/s** below ATCF (median −2.3, heavy
  tail); 3→6 km pooling accounts for −1.7 of it. About half the lifecycle strong-band
  under-bias is inherited from the data, so a "bias → 0" gate is mis-specified by ≈ −4 m/s.
- [ ] Inspect ~20 tail frames (grid−ATCF < −10 m/s): vortex centring within the crop,
  inner-core wind and the HAFS tracker's source. Decide whether to drop or flag them in
  the intensity inventory. They sit in the ≥58 band that `cfg_intense_epochs` oversamples.
- [ ] **(b) Token sweep (OSSE, inference only).** Fix all observations, sweep the ATCF
  Vmax token over 20–70 m/s on ~30 held-out HAFS cases at CFG 1 and 1.5, and plot
  generated per-member grid Vmax against the token and against (a)'s truth relationship.
  Slope < the truth slope is conditioning regression-to-mean → test an ATCF-only
  guidance scale (compositional CFG) and a best-track likelihood on the radial-max
  functional (center-tolerant, per I12).
- [ ] **I21 floor:** Holland profile from ATCF Vmax/RMW/R34 scored on the Anggrek
  162/132 pairs and the frozen test.
- [ ] **Populate R34 + motion** in unified real/lifecycle inference (I9 prerequisite);
  identical-seed on/off ablation for the R34 bias.
- [ ] Storm-bootstrap CIs + fair CRPS + rank histograms (F item 2, I15) before judging
  the intensity-balanced run.

**ERA5 pilot result (2026-09-24):** Gaussian, ERA5 t=0.15 and ERA5 t=0.4
matched two-member runs completed on one held-out SAR/ERA5 fix. The light
t=0.15 start lowered in-swath MAE from 2.380 to 1.829 m/s on that fix, whereas
t=0.4 suppressed peak winds and ensemble spread. See
[ERA5 midpoint-start pilot](details/era5_background_start_pilot.md). One-case
feasibility only; no population or outside-swath truth claim.

**Intense-epoch training status:** first Slurm attempt reached ~315 batches in
its first 10,000-frame epoch but failed because validation was scheduled at
batch 500, after the iterable epoch ended. Corrected `val_check_interval=250`
and restarted as `intensity_10k_rotnoise_proxy_v2` (Slurm 4838187). Validation
was logged at step 249; the run remains active. Natural control 4820743
completed all 10,000 steps. Do not mark the augmented arm evaluated until its
checkpoint and stratified metrics are available.

**2026-09-24 live check:** `intensity_10k_rotnoise_proxy_v2` was RUNNING
(Slurm 4838187) after step 7,488; best logged validation field RMSE 2.465,
versus the natural control's final/best 2.242. The early-stopping metric issue
is resolved: validation appears at step 249 and subsequent short epochs.
Treat the comparison as provisional until job completion.

---

## N — Conditional neural field (I28, 2026-09-24)

Track plan and log: [tracks/neural_field_plan.md](tracks/neural_field_plan.md). Code on
branch `neural-field` (worktree `maxss-ml/.claude/worktrees/neural-field`).

**Done (details and numbers in the track plan):**
- [x] Stage 0 representation ceiling (gate passed 2026-09-24) and Stage 1 OSSE inversion; LSD / high-k metrics.
- [x] I31 BT output head: ABI B13 (param 58) chosen by `bt_dvorak_sim`; `nf_bt_head` → `nf_bt_core` (core sampling, adopted)
  → `nf_bt_sig` (SIGReg, adopted); calibrated BT ring-profile likelihood (I32 step 1). IR alone stays weak on intensity.
- [x] Temporal: predictor / AR / persistence dynamics, balanced prior (largest single sim lever), corrected-data retrain
  `nf_bt_temporal_fix_0000` (reference per-frame model); `nf_bt_slow` neutral; `nf_bt_ibal` better strong/extreme in sim, on real
  data worse on Anggrek but best strong band on the scoreboard with the scat lower bound.
- [x] Real data (E3/E4): Anggrek lifecycle and frozen 2023 SAR scoreboard drivers (`nf_real_lifecycle`, `nf_real_scoreboard`,
  SAR patch parity); V05 intercalibrated obs; 24-h window fit (removes the sensor see-saw); 43-km scalar-box radiometer operator
  (calibrated on 1.7k SAR collocations); scatterometer lower bound (`scat_censor`); per-sensor coverage diagnostic in benchtools.
- [x] JEPA IR intensity term (`scripts/jepa_ir_vmax.py`, kept; replaces the best track at no cost). IR-conditioned linear
  latent prior v1 (`nf_ir_prior`) **dropped**: 8 % of latent variance, decoded means 8–16 m/s too weak (→ I39).
- [x] Time-offset decoder input (`nf_bt_tau02`): small Anggrek gain (Vmax MAE −0.1), none on the scoreboard; not a major lever.
- [x] Time as a decoder coordinate (I30): single-latent window `nf_bt_window_0000` (capacity-limited; best R34 / scoreboard
  overall Vmax) and **knot window model `nf_bt_wknot5_0000`** (5 latents every 6 h; adopted).
- [x] Scat lower-bound threshold sweep 15/20/25 on V05 (2026-10-13): Anggrek best at 20–25; on SAR scenes every bound
  over-shoots the knot model (no bound best overall) → conditional bound below.
- [x] Design doc `src/maxss_diff/neural_field.md`; HTML reports `.../tmp/qfebvre/maxss/{nf_knot_report,product_bench_report}/`.

**Current baseline (2026-10-13):** knot window model + V05 + 43-km radiometer box + JEPA IR intensity term, no best track.
Anggrek (scat LB 20): Vmax MAE 3.90, bias 0.0, RMW MAE 14 km, R34 MAE 21.7 km. 2023 SAR scoreboard (no LB): Vmax MAE
4.26 / 4.78 / 10.11 (flow 4.38 / 4.39 / 5.42), speed RMSE 2.55 (2.48), direction 19° (35°).

**Open:**
- [ ] **N-L Conditional scatterometer lower bound**: `scat_censor_mode` = `no_sar` (lifted when SAR is in the frame) /
  `core_only` (≤ 150 km); target = keep Anggrek's 3.8–3.9 while removing the scoreboard over-shoot (strong band 10.1 → ≤ 8 without
  weak/moderate loss). Runs queued 2026-10-14 (Anggrek ×2, scoreboard ×2, historical no_sar).
- [ ] **N-D Fine-structure deficit split** ([ideas.md I35](ideas.md)): ceiling vs MAP vs shell vs truth spectra / LSD /
  eyewall gradient / Rmax / Vmax by band on the mem1001 panel → decides I39 vs I38.
- [ ] **N-P Probabilistic NF**: I39 conditional latent flow prior (SSL-conditioned, gives members; successor of IR prior v1)
  then I40 trajectory prior (see ideas.md); gate on mem1001 + Anggrek + scoreboard CRPS / spread-skill.
  - [ ] I39 v1 (kicked off 2026-10-14, `maxss_diff/nf_latent_fm.py`): flow matching on the knot model's whitened window code
    (2,560-d) conditioned on 9 JEPA CLS IR embeddings + sin(lat), CFG dropout; chain collect → embed → train (`nf_lfm_wknot5`) →
    IR-only ensemble eval (per-member Vmax by band, spread vs error, vs Gaussian prior mean). Next: posterior sampling with the
    sensor operators (guided sampling), then use as the window-fit prior.
- [ ] **N-B Product test bench** ([ideas.md I36](ideas.md)): products, paths and first results in the track plan
  (2026-10-12; report `.../product_bench_report/`).
  - [ ] NF knot on the historical 2014–2020 SAR panel (job 1190164; no IR intensity term, the JEPA ridge trained on those
    seasons); the report regenerates automatically.
  - [ ] 25-km common-smoothing scores; independence / assimilation flags table.
  - [x] Pre-2014 (2010–2013) reference obs compiled (358 storms, ASCAT-A/B + SMOS + ERA5, V05 processing; 2026-10-13) →
    `results_hafs/ref_data/V05_pre2014`.
    - [ ] `cfg_recalibrated` (era5_recalibrated), then a scat/rad-truth product panel (MAXSS L4, Herry, ERA5, NF) — consistency
      check only (MAXSS assimilates those obs).
  - [ ] CCMP for every storm 2010–2026, per-year batches (`scripts/ccmp_yearly_driver.py`, running since 2026-10-13; ≈ 195 GB
    downloaded over ~1.5 days at 12 streams, ≤ ~12 GB cached at once, ≈ 30 GB of storm extracts kept); then the CCMP rows of the
    2023 and historical panels.
- [ ] **N-A Asymmetry metrics** ([ideas.md I37](ideas.md); benchtools `metrics/asymmetry.py`): quadrant size/shape split,
  ranking, wavenumber-1 amplitude / phase vs SAR (≥ 270° azimuth), optional inflow by quadrant; align with Herry's
  `comparison_SAR` evaluations.
- [ ] **N-F Fine scales with temporal coherence** ([ideas.md I38](ideas.md)), after N-D: residual flow matching on the NF window
  (CorrDiff-style, 9 time channels) and, in parallel, a spectrum-informed multi-stage residual NF.
- [ ] Housekeeping: refresh the NF knot report with the scoreboard LB sweep; commit the `neural-field` branch (nothing committed
  yet; user decision).
- Flexlock run.lock fix: branch `fix/single-task-runlock` (commit 5321cd4, worktree
  `2509_flexlock/flexlock-release`) **shelved 2026-09-24** by user decision; unpushed.

**Broader intensity validation (2026-09-24):** the natural and intense training
runs both completed at 10,000 steps. Their *training* validation stream was
identical and unbalanced. A separate paired 160-case HAFS validation panel has
40 cases per grid-Vmax band; the >=58 m/s band improved from 3.255 to 2.879
m/s field RMSE and from 16.432 to 9.328 m/s Vmax MAE with the intense recipe,
while <33 m/s RMSE worsened from 1.722 to 1.812. Details, CRPS and storm-block
intervals: [intense-epoch validation results](details/intensity_balanced_validation_results.md).
This is simulation validation; real-storm transfer remains to be tested.

Broad ERA5-start inference was also submitted for up to 63 matched SAR/ERA5
acquisitions across 39 canonical real-validation storms, with at most two fixes
per storm and four paired members. The Gaussian control is Slurm 4868588; the
t=0.15 arm is Slurm 4868625. Both use the same <=90-minute ERA5 availability
filter. Their case lists and real-SAR metrics must be checked before promotion.

**Broad ERA5-start result (2026-09-24):** corrected paired runs completed on
62 real SAR acquisitions from 39 validation storms (Gaussian Slurm 4869480,
ERA5 t=0.15 Slurm 4869555). Midpoint starts brought out-of-swath fields closer
to ERA5 but worsened SAR RMSE, CRPS and high-intensity ATCF Vmax MAE; ensemble
spread fell. Do not promote. See
[broader ERA5-start results](details/era5_background_start_broad_results.md).
A low-frequency/outer-field background guidance test remains open.

**Intensity-to-SAR continuation (2026-09-24):** The HAFS intense checkpoint
has completed tcwindbenchtools OSSE and 2022 OSE scoring. An opt-in real-SAR
fine-tune uses all >=45 m/s training acquisitions each 1,000-item epoch with
physical rotations and 0.25 m/s smooth target noise; Slurm 4890210 is running.
The held-out 2022 OSE and Anggrek lifecycle dumps and tcwindbenchtools scores
are queued as success-dependent jobs using the updated GPU directives. The standard 256-case OSSE had no strong
cases, so a fixed 40-per-band OSSE panel is also queued for benchtools scoring.
See [the job and result ledger](details/intense_sar_finetune_tcwindbench_eval.md).
