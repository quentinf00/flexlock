# TODO

Accepted implementation scope only. Promote an item from [IDEAS.md](IDEAS.md)
after its goal, cost, and decision gate have been agreed. Record the outcome in
[DONE.md](DONE.md) with a date.

## Active

These three are open because a run finished and nothing was concluded from it,
not because they were planned as scope. They are listed as *pending
confirmation* — each states the evidence it rests on so it can be closed or
promoted quickly.

### T1 — Close out the MAE result properly

- **Origin:** [DONE.md](DONE.md#mae-with-scattering-targets--first-learned-sat-encoder-to-beat-the-fixed-floor-2026-07-30) — `fable2b_mae_scat`, finished 2026-07-30, never written up.
- **Status:** **superseded 2026-09-30 by T4.** The offline probe now exists for the
  MAE recipe on every band set (`results/band_*/linear_probe_*`); MAE is the
  default sat objective on IR. `fable2b_mae_scat` itself trained on the 37V/91V
  swap and is not worth probing. Close when T5 reports.
- **CLOSED 2026-10-10** — T5 reported (closed 2026-10-03) and MAE was itself superseded as the
  sat recipe by faithful LeJEPA (IDEAS I1 rejected 2026-10-09).  Nothing left to run.

**Why it is open:** the arm cleared its decision gate by a wide margin
(inline `vmax` R² 0.644 vs the 0.379 scattering floor and the 0.290 temporal-JEPA
baseline) and the control arm `mae_pix` did not (0.372) — but the number comes
from the in-training `LinearProbeCallback`, not the offline `linear_probe`
stage, so it is not comparable to any table in [DONE.md](DONE.md) as it stands.

**Scope:**

1. Run the offline `linear_probe` stage on `fable2b_mae_scat` and
   `fable2b_mae_pix` checkpoints, with `encoder_pool=avg` honoured, and report
   the full label set (not just vmax) against the existing bracket.
2. Record the outcome in [DONE.md](DONE.md) and state explicitly whether MAE
   also moves `rmw` / `r34` / `delta_vmax`, or only static intensity.
3. Decide, on those numbers, whether MAE becomes the default sat recipe.

**Non-goals:** the scale-up arms (longer, 256 px, wind, patch 8) — those are
[IDEAS.md](IDEAS.md) I1 and should be promoted separately once the offline
numbers exist.

**Completion criteria:** an offline probe table for both arms in
[DONE.md](DONE.md), and either a promoted default or a stated reason not to.

### T2 — Explain the zarrpatch MAE regression

- **CLOSED 2026-10-13 (obsolete).** Both confirmation arms (3167717, 3168443) crashed at start on
  2026-08-17 (flexlock `run.error`, no metrics) and were never rerun, so "confirmation running" was
  stale.  The question no longer has a consumer: training moved to the faithful LeJEPA trainer on
  `.npy` frame corpora; zarrpatch is used only by benchmark / smoke scripts.  Kept: the shuffle-buffer
  fix in `data/zarrpatch.py` and the parity result (reader not the cause).  Reopen only if zarrpatch
  becomes a training path again.
- **Origin:** `results/fable2b_mae_scat_zarr_b16`, 2026-08-01.
- **Status:** cause identified, confirmation running. **Still blocks adopting zarrpatch
  as the default loader until the two arms below report.**

**Update 2026-08-17 — scope items 1 and 4 are done; the reader is not the cause.**

*Item 1.* Ran `scripts/verify_zarr_webds_parity.py --modality sat --split train
--samples 24`. Metadata 24/24, labels 24/24, mask mismatch 0.0,
`physical_mismatch_fraction` **9.3e-05**. `pixel_pass: 0` is an artefact of the
script's own `atol=2e-3` being tighter than fp16 round-off — webds stores
normalized fp16, zarr stores physical fp16 and normalizes live, so they quantize
at different points. Residual is RMSE 0.00306 / max 0.0142 in z-score units, i.e.
**16× below the `input_noise_std=0.05` we inject on purpose**. That cannot take
`train/mae_loss` from 0.41 to 0.91.

*Item 4, cause.* `data/zarrpatch.py` accepted `decode_shuffle_buffer` and
`raw_shuffle_buffer` and then **never stored or used them** — it hardcoded
`shuffle_buffer="auto"`. `params.decode_shuffle_buffer=2000` therefore applied to
the webds path only. zarrpatch's `"auto"` is 4× the largest patches-per-block
count, which on this epoch (29,616 patches / 7,286 groups, patches/group median 4,
max 12) resolves to **48**. Measured effect on batch composition:

| shuffle buffer | distinct storms per batch of 32 |
|---|---:|
| `"auto"` (≈48) | 17.27 (min 11) |
| 2000 | 28.80 (min 26) |

Fixed in `data/zarrpatch.py` (store both, use `decode_shuffle_buffer or "auto"`).

*Item 2, running.* Two arms queued, each otherwise reproducing `fable2b_mae_scat`
exactly (`max_epochs=60`, `input_noise_std=0.05`, `normalize_pred_targets=true`,
`mae_mask_ratio=0.75`, `mae_target=scatter`):

- **3167717** — webds @ batch 16 → `results/fable2b_mae_scat_b16`. Isolates batch
  size on a trusted loader. If this collapses too, batch size was the cause.
- **3168443** — zarr @ batch 32 with `decode_shuffle_buffer=2000` →
  `results/fable2b_mae_scat_zarr_b32_shuf2000`. Go/no-go on the fixed loader.

*Still open, not covered by either arm:* the zarr b16 run logged **no `val/*`
metrics at all** even though `results/val_artifacts/zarr_sat_ctx8_pred8_*.h5`
exists (4.7 GB) — worth a separate look, since it also cost us the `val/loss`
comparison. Item 3 (6 train / 1 val storms missing from `slim128`) is untouched.

**Why it is open:** the same MAE-scatter objective run through the zarrpatch
datamodule at batch 16 reaches an inline `vmax` R² of **0.036** over 60 epochs,
against 0.644 on the webds path. That is not a small regression — it is the
difference between the best encoder in the project and no signal at all, and
the two runs differ in both loader and batch size, so neither is ruled out. The
run log also shows `train: 6 storms are not present in slim128 yet` /
`val: 1 storms`, i.e. the two paths did not see the same data.

**Scope:**

1. Run `scripts/verify_zarr_webds_parity.py` on the sat slim128 split and record
   the result — this is exactly the question it was written for.
2. Separate the two variables: one zarrpatch run at batch 32, or one webds run
   at batch 16.
3. Resolve the missing-storm gap (backfill slim128, or make the comparison use
   the intersection).
4. Record the finding in [DONE.md](DONE.md); if the cause is in
   `data/zarrpatch.py`, fix it there.

**Completion criteria:** a stated cause, and a go/no-go on making zarrpatch the
default training loader.

### T3 — Port `cross_cycle` off the tar-handle pool

- **CLOSED 2026-10-13 (deferred with IDEAS I16).** Depends on T2 (obsolete) and serves only the
  cross-cycle invariance run, which stays deferred.
- **Origin:** dataloading plan step 3.3, carried over past the memmap decision — see [IDEAS.md](IDEAS.md) N8.
- **Status:** pending confirmation; low urgency.

**Why it is open:** `data/cross_cycle.py` bypasses the dataloader stack with a
per-worker `tarfile` handle pool (`_TarPool`) precisely because it needs random
access to two samples per item. With the zarrpatch reader that becomes two row
lookups plus two window slices, and the dependency on per-storm
`train_seqs-{storm}.tar` naming — the last consumer of the orig256 layout apart
from native-resolution runs — disappears.

**Scope:** port `_CrossCycleDataset` to the zarrpatch reader, delete `_TarPool`,
keep `t0_min` filtering and the paired-view output contract. It is the hardest
consumer of the reader, so it validates the migration.

**Non-goals:** launching a cross-cycle *training* run — that is
[IDEAS.md](IDEAS.md) I16 and is deferred on the evidence in
[DONE.md](DONE.md).

**Completion criteria:** the cross-cycle smoke test passes on the zarrpatch
path, `_TarPool` is gone, and T2 has been resolved first (this inherits any
zarrpatch correctness bug).

### T4 — Band suite: rebuild the sat bracket on real band choices

- **CLOSED 2026-09-30** (see status below); follow-ups were absorbed by T5, T7, T10, T12, T14.
- **Accepted:** 2026-09-26
- **Origin:** [DONE.md](DONE.md#the-sat-ir-bands-were-passive-microwave--every-sat-conclusion-re-opened-2026-09-26)
- **Status (2026-09-30):** floors ✔, supervised ✔ (6), MAE trained ✔ (5), offline
  probes ✔ (10). Results in DONE.md. Gate 1 answered: MAE beats its floor on every
  set (+0.05 … +0.20 vmax). Gate 2: the "ceiling" is beaten by frozen MAE on ir/abi
  → it is a from-scratch baseline, not a ceiling. Gate 3: SSMIS gives the best
  *supervised* result, but frozen MAE on IR alone (0.786) ≈ all 8 (0.783).
  **Closed 2026-09-30**: default = IR (`params.sat_channel_indices=[3]`,
  `slim128_all8`), IDEAS "Where the project stands" rewritten. Open follow-ups
  (single-band MAEs, JEPA-on-IR re-test, scale-up, dynamics, IRAR transfer) belong
  in new items once scoped.

**Goal:** floor / SSL / ceiling measured on identical, deliberately chosen inputs
for each band set, replacing the 37V-only bracket.

**Scope** (`scripts/run_band_suite.sh <stage> <set>`, dirs `results/band_<set>/`):

| set | bands (zarr idx) | train (MAE-scat, 60 ep) | supervised ceiling (vmax R²) |
|---|---|---|---|
| `ir` | 3 | MAE probe 0.786 | 0.719 |
| `abi` | 0–3 | MAE probe 0.776 | 0.714 |
| `mw` | 4–7 | MAE probe 0.756 | **0.803** |
| `all` | 0–7 | MAE probe 0.783 | 0.784 |
| `legacy2` | 5, 6 stacked | MAE probe 0.794 | 0.799 |
| `legacy37v` | 5 | — | 0.725 |

Then `probe <set>` for each trained arm (offline `linear_probe`, GAP key for MAE).
Floors: `results/band_floors/results.md` (done).

**Decision gates:**
1. Does any learned encoder beat its own band set's floor (all-8: domain 0.732 /
   scattering 0.734)? If not, SSL on sat adds nothing a fixed transform doesn't.
2. Does the supervised ceiling on all 8 bands clear the floor meaningfully? If the
   ceiling ≈ floor, sat intensity is saturated and effort should go to dynamics
   (`delta_vmax`, where all-8 scattering is 0.161).
3. `ir` vs `mw`: which modality carries the signal — decides the default band set
   and whether IRWIN/SARGEO transfer is worth keeping as a constraint.

**Non-goals:** temporal-JEPA arms (T0.3 closure is band-independent); zarrpatch
path (still hardcoded to bands 5/6 — `data/zarrpatch.py:278`).

**Completion criteria:** a band-set bracket table in DONE.md, a new default
`params.sat_channel_indices`, and IDEAS "Where the project stands" rewritten.

### T5 — Re-test temporal JEPA and frame invariance on IR

- **Accepted:** 2026-09-30
- **Origin:** IDEAS "Where the project stands" (triage: "worth one cheap re-test").
- **Status: CLOSED 2026-10-03** — both arms fail on IR (DONE.md, "T10 grid complete + T5
  closed"); the open question moves to T10 step 8 (view construction). History:
  `ir_jepa` trained (60 ep, 54 min); probing it through the same
  CPU harness as MAE / DINOv3 (`irar_probe pool=cls`, `extract_seq_embeddings` →
  `dynamics_probe`). `ir_lejepa_frame` crashed at step 0 — `view_augment` mixed fp16 slim
  frames with fp32 grids under bf16 autocast; fixed (augmentation now runs in fp32) and
  resubmitted (job 194772).

**Why:** every sat verdict on these objectives (temporal JEPA 0.26–0.29, §0.5
invariance "structurally closed") was measured on the 37V/91V random swap and
scored on 37V — uninterpretable. Temporal JEPA reaches 0.74 on wind, so the
objective can learn intensity from a sane input. JEPA is also the only objective
with a predictor, so its latent +24 h probe is the direct test of learned dynamics.

**Scope** (`scripts/run_ir_suite.sh`): same recipe as the old runs, IR default input,
60 epochs, 1 seed.
- `jepa` — temporal JEPA, the `fable2b` `baseline_sat` recipe (lr 1e-4, wd 1e-3,
  LayerNorm targets, input noise 0.05), CLS readout. *Correction 2026-10-02:* this is
  **not** the `sat_qw` recipe — `sat_qw` also ran hierarchical cluster resampling with
  centroid invariance (weight ramped to 0.1, 200 epochs). Here `cluster_every_n_epochs=0`,
  so the invariance weight stays 0 for the whole run (checked in the logged
  `train/invariance_weight`): the loss is pure prediction + SIGReg.
- `lejepa_frame` — frame-level LeJEPA round 1 (4 physically screened views, no
  predictor, batch 64). Round 2's channel views do not apply to one band.
- then `CKPT=last` and `CKPT=best_probe` offline probes for both (`probe` stage;
  JEPA's probe includes the predictor latent probe for `delta_vmax_24h`).

**Reference:** IR MAE (`results/band_ir`) vmax 0.786 GAP / 0.760 CLS; IR floor 0.587;
IR supervised 0.719; `delta_vmax_24h` MAE 0.160, track-scalar baseline 0.246 (T6).

**Decision gates:**
1. JEPA vmax probe ≥ IR floor 0.587? If not, the temporal objective is closed for sat
   for a reason that no longer depends on inputs.
2. JEPA latent +24 h or `delta_vmax_24h` probe > MAE's 0.160 — the only reason to keep
   a temporal objective; compare against the track-scalar baseline 0.246.
3. `lejepa_frame` vmax ≥ 0.587: re-opens N1 (invariance) for IR, else N1 stands on
   the round-1 mechanism alone ("physically screened augs are too easy").

**Completion criteria:** probe tables for both arms in DONE.md; N1 and fact 3 in IDEAS
restated or confirmed.

### T6 — Dynamics: what do images add over track scalars?

- **CLOSED 2026-10-13.** Steps 1–3 done (gate passed on HAFS 2026-10-01); step 4 (JEPA latent
  probe) answered by the temporal-JEPA re-tests (T5; `tjepa` arms 2026-10-08: no Δv gain; I13 /
  I17 / I18 / I20 / I23 retired).  The dynamics question continued in T7 4c, T12 and T14.
- **Accepted:** 2026-09-30
- **Origin:** IDEAS I4, I6, "Where the project stands" fact 2.
- **Status (2026-10-01):** steps 1–3 done; **gate passed on HAFS** — image+scalars GBM
  0.362 vs scalars 0.250 at 24 h, ΔR² +0.11 [+0.06, +0.17] storm bootstrap; 48 h +0.12
  [+0.04, +0.21]; RI-AUC 0.77 → 0.81. GRU over 8 frames ≈ mean embedding (+ scalars).
  Results in DONE.md. Step 4 (JEPA latent probe) waits on T5. Next, now that real-data
  numbers exist (T7), the dynamics question moves to IRAR (non-circular).

**Finding that frames the work** (val = the probes' exact 2932 windows, verified
identical): track scalars known at the anchor frame, no imagery —

| features (GBM) | Δvmax 24 h R² | Δvmax 48 h R² | RI-AUC (≥30 kt/24 h) |
|---|---:|---:|---:|
| lead time only | 0.00 | 0.00 | 0.47 |
| vmax, \|lat\|, lead (I6) | 0.13 | 0.26 | 0.53 |
| + 12 h / 21 h intensity trend | 0.19 | 0.28 | 0.69 |
| + mslp, translation speed, rmw | **0.25** | **0.30** | **0.77** |
| best image model so far (IR MAE / supervised) | 0.16 – 0.22 | 0.23 – 0.28 | — |

The bar for "images help dynamics" is 0.25 / 0.30, not 0. Lead time carries no Δvmax
signal (I4 answered for dynamics; still open for intensity labels).

**Scope:**
1. ✔ Baselines (`scripts/dynamics_baselines.py`).
2. **Image + scalars**: add the `clim+` scalars to the frozen-embedding probe (Ridge
   and GBM on `[embedding ‖ scalars]`) for IR MAE, and later T5's arms. This is the
   actual question: does the image add to what the track already says?
3. **Temporal head on frozen embeddings**: small GRU/transformer over the 8 context
   embeddings (+ scalars) → Δvmax 24/48 h; the context trend is the part a per-frame
   Ridge on the mean embedding cannot use.
4. **JEPA latent probe** from T5.

**Decision gate:** image+scalars must beat `clim+` GBM by more than the storm-level
bootstrap CI (I2 — build it as part of this item) on Δvmax 24 h, else dynamics from
sat imagery is not demonstrated on HAFS and effort shifts to T7 (real data), where
the scalars are best-track values rather than the model's own tracker.

**Caveat:** labels are HAFS self-consistency (I8): Δvmax is the model's own future,
so the track scalars are *the same model's* state. T7 is where this stops being
circular.

### T7 — Transfer to real data: HAFS-IR encoder on IRAR (best track)

- **CLOSED 2026-10-13.** Gate (a) passed 2026-10-01; gate (b) answered 2026-10-09
  (`irar_only_nophoto`: real-only pretraining works, HAFS + IRAR better on both domains); 4b
  wavelength shift done 2026-10-02 and re-checked 2026-10-11 (no penalty); 4c dynamics on IRAR is
  the standard `irar_probe` Δv24 / Δv48 GRU + scalars; 4d encoder comparisons done throughout T10–T14.
  Remaining follow-up (major-hurricane regression-to-mean bias) moved to IDEAS I29.
- **Accepted:** 2026-09-30
- **Origin:** IDEAS I8; `docs/satellite_bands.md` §5.
- **Status (2026-10-01):** steps 1–3 done, **gate (a) passed** — frozen HAFS-IR MAE on
  real IRAR (season hold-out 2023–24, 132 storms): best-track vmax R² 0.833 / 12.3 kt
  vs scattering floor 0.646 (+0.19 [+0.15, +0.23]); Δvmax 24 h image+scalars +0.06
  [+0.01, +0.10] over best-track scalars. Results in DONE.md.

**Next steps (in order):**
- **4a. IRAR-pretrained control (gate b)** — same MAE recipe trained on the IRAR cache
  (2017–2022 storms only, so the test seasons stay unseen). Needs a training
  datamodule over `results/irar_cache` (frames + 3-hourly sequence index); GPU.
  Then a HAFS→IRAR fine-tune arm. Answers "does synthetic HAFS add value beyond the
  real archive?".
- **4b. Wavelength shift** — rerun `irar_probe` with `wavelengths=[10.6,11.3]`
  (GOES-13/15, Meteosat SEVIRI, ~8.6 k frames): does the encoder degrade off ABI B13?
  CPU, cheap. ✔ *Done 2026-10-02*: no collapse (vmax 0.772 / 13.0 kt vs floor 0.583),
  but confounded with basin and a small test set (889 windows) — see DONE.md.
- ✔ *Done 2026-10-02*: 24 h history readouts + per-category RMSE/bias (DONE.md). Open
  follow-up: the regression-to-mean bias on major hurricanes (Cat 3–5 −5 to −12 kt
  even with the GRU) — try a calibration step (isotonic on train) and a loss that
  weights the tail, and report per-category alongside every future vmax number.
- **4c. Dynamics on IRAR** — port `dynamics_probe`'s GRU + scalars head to IRAR
  windows (best-track scalars, non-circular), with RI-AUC; compare to a SHIPS-style
  scalar baseline.
- **4d. Encoder comparison** — rerun `irar_probe` for T5's JEPA / invariance arms and the
  other band-suite encoders that include band 3 (abi, all): does IR-only pretraining
  transfer best?

**Why:** everything so far scores agreement with HAFS's own tracker on synthetic
imagery. IRAR is real geostationary IR (the same physical band as HAFS idx 3) with
best-track labels, global, 2017–2024, 10–15 min cadence — the test of whether the
HAFS-IR features mean anything operationally.

**Data facts** (`/scale/project/ifremer-isi-jumeaunumerique/IRAR_BestTrack_corrected`,
`{year}/{basin}{nn}{year}/TC-IRAR_v02r02_*.nc`, ~80 k files/yr):
- `ir_aeqd` — storm-centred azimuthal-equidistant 501×501 @ 2 km (±500 km),
  upsampled from a 4 km Mercator remap; 0.5 K / 1 K quantisation.
- band varies by satellite: GOES-16/17 ABI B13 10.3 µm, Himawari AHI B13 10.4 µm,
  SEVIRI 10.8 µm, GOES-15 10.7 µm, Meteosat-7 11.2 µm (`band_wavelength` per file).
- labels per image: `storm_intensity` (kt, best track interpolated), Dvorak CI,
  position, motion, distance to land, R5; `%` pixels below 273…203 K.

**Scope:**
1. **Loader** `hafs_jepa/data/irar.py`: crop `ir_aeqd` to ±384 km (384 px), area-
   downsample ×3 → 128 px @ 6 km (the HAFS 128-px geometry); z-score with the HAFS
   band-3 stats (mean 272.14 K, std 25.90 K, from `webds/sat/sat_stats.json`) so the
   frozen encoder sees its training distribution; NaN → mask. Sequences: subsample
   to 3 h spacing so 8-frame contexts match HAFS (24 h). Storm-level split, plus a
   season hold-out (I9). Start with ABI/AHI B13 only (10.3–10.4 µm); SEVIRI /
   older sensors as a separate wavelength-shift test.
2. **Floors on IRAR**: domain + scattering (reuse `_sat_domain_features`,
   `Scattering2D`) → best-track vmax, Δvmax 24 h.
3. **Zero-shot frozen probe**: HAFS-IR MAE (`results/band_ir/train/checkpoints/last.ckpt`)
   → Ridge on IRAR labels. Same for T5's winners.
4. **Controls**: IR MAE pretrained on IRAR itself (same recipe) — separates "HAFS
   features transfer" from "MAE on IR works"; then fine-tuning.
5. Report RMSE in kt next to published IR-only intensity estimators (ADT / deep-IR
   methods, typically ~10–13 kt RMSE vs best track) as external context.

**Decision gates:** (a) zero-shot HAFS-IR probe ≥ IRAR floors → HAFS pretraining
transfers; (b) HAFS-pretrained ≥ IRAR-pretrained → synthetic data adds value beyond
the real archive; (c) Δvmax on best track vs a best-track scalar baseline (T6
analogue, now non-circular).

**Risks:** synthetic-vs-real appearance gap (HAFS microphysics, no parallax/limb, 2 km
native vs 4 km remap); wavelength drift across satellites; IRAR's cadence is far denser
than HAFS's 3 h — decide early whether to exploit it (temporal objectives) or match it.

### T9 — TCBench: score HAFS and our IR intensity forecasts on the 2023 benchmark

- **Accepted:** 2026-10-02
- **Origin:** user request; repo `260324_jepa/TCBench` (github.com/tcbench/TCBench, code only).
- **Status (2026-10-06):** step 2 done — IR forecaster entries scored (DONE.md: image adds
  1.4–1.7 kt at 48–72 h; beats HAFS ≤ 12 h with a best-track-init caveat, loses ≥ 48 h). Next:
  real-time init variant (adeck CARQ) for a fair operational comparison; quantile heads → CRPS.
  References added 2026-10-06 (Pangu, AIFS, FourCastNet, GEFS, GenCast; `results/tcbench_2023.md`).
  Candidate next entry: hybrid — AI-model (Pangu) track + IR intensity, scored on both axes.
  RI track (2026-10-06): only HAFS has skill (CSI 0.12, DONE.md); TCBench's own RI flags are
  buggy (recomputed in `scripts/tcbench_ri.py`). Candidate: probabilistic RI classifier (IR
  history + scalars, SHIPS-RII style), threshold tuned on train for CSI → RI entry; also report
  Brier / AUC since flags discard probability. Consider reporting the RI-flag bug upstream.
  *Done 2026-10-06:* `scripts/tcbench_ri_classifier.py` → CSI 0.192 vs HAFS 0.104 on the homogeneous
  sample (IR − HAFS +0.088 [+0.006, +0.177]); image adds ≈ nothing over scalars. Next for all T9
  entries: **real-time init** (adeck CARQ / ADT instead of post-season best track) — the decisive
  fairness fix, since the classifier leans on the 12/24 h intensity trend.
  *Done 2026-10-06 (imagery-only variant, `scripts/tcbench_ir_realtime.py`):* init intensity from the
  IR nowcast (8 kt MAE) — intensity loses to HAFS from 24 h, RI CSI 0.151 vs 0.104 (n.s.). Remaining
  fairness gap: real-time positions/ADT vs our best-track positions (minor). Ideas to improve the
  imagery-only system: GRU nowcast (0.904 vs Ridge 0.88), ensemble/quantile heads, more seasons.
- **Status (2026-10-02):** step 1 done — env, IBTrACS, persistence, HAFS entry scored
  (DONE.md), climatology too (upstream quirks noted there). Next: step 2.

**What TCBench scores:** deterministic / ensemble forecast tracks for the **2023** test
year (schema: SID, init time, valid time, wind max kt, pressure min hPa, lat, lon), on the
6-hourly grid with 00/12Z inits and 6–120 h leads, against IBTrACS (USA wind): position
errors (DPE, along/cross), intensity AE/SE, CRPS for ensembles, RI detection
(`evaluate_tracks.py`, `evaluate_tracks_RI.py`, `metrics.py`). Also a Δintensity task with
climatology / MLR / CNN baselines (`baselines.py`). No data ships with the checkout.

**Scope:**
1. **Pipeline + references**: IBTrACS CSV (convert the local
   `250930_maxss_era5pp/data/IBTrACS.since1980.v04r01.nc`, which carries `usa_atcf_id`,
   or download the official CSV); TCBench env (`requirements.txt`, incl. huracanpy);
   entries: **HAFS operational forecasts** from `atcfunix.parquet` (2023: 103 storms,
   974 cycles at 00/12Z, leads ≤ 126 h), **persistence**, **climatology**. Validates the
   pipeline and gives a strong regional-model reference.
2. **Our IR intensity forecaster**: vmax(t+lead) = best-track vmax(t) + Δ̂(lead), Δ̂ from the
   24 h IR history + init-time track state (T6/T7 model), one head per lead 6–120 h,
   trained on IRAR 2017–2022 (2023 is in our hold-out → no leakage); positions from
   persistence (or HAFS track), labelled as such — only intensity/RI metrics are ours.
   Quantile heads → CRPS.
3. Reference AI-model tracks (Pangu / AIFS / GenCast) if the TCBench team's files can be
   obtained — **ask the user for the location**.

**Fairness note:** our model and SHIPS-style baselines start from best-track intensity at
init; global AI models start from analyses and under-predict intensity. The bar is
persistence / climatology / TCBench Δintensity baselines first, then HAFS; any comparison
with AI weather models states this asymmetry.

**Not in TCBench:** current-intensity estimation (lead 0; T7: 0.876 / 10.6 kt) — keep
reporting it separately.

### T10 — Frozen DINOv3 ViT-S/16 as an alternate backbone (is HAFS pretraining worth it?)

- **Accepted:** 2026-10-02
- **Origin:** user request — github.com/facebookresearch/dinov3, ViT-S/16 distilled.
- **Status (2026-10-09):** question answered — HAFS-domain SSL (faithful LeJEPA, no jitter)
  beats frozen DINOv3 on HAFS and real IR; old failures bisected (pooled SIGReg × BN-less
  projector) and fixed in the Lightning module (validation run pending). Remaining under T10:
  only the validation arm; headroom work moves to IDEAS I10 (256 px).
- **Status (2026-10-02):** steps 1 + 3 (128 px) done — **frozen DINOv3 beats the HAFS-IR
  MAE on real IR on every readout** (GRU 0.895 / 9.7 kt vs 0.876 / 10.6; majors' bias
  removed; DONE.md). Running: IRAR at 256 px, HAFS per-frame extraction at 256 px →
  `dynamics_probe` (the HAFS-domain side of the gate).

**Question:** does a generic natural-image foundation model, frozen, match our
HAFS-trained IR MAE on HAFS and on real IRAR? If it does, training from scratch on HAFS
buys little; if not, domain pretraining is justified.

**Backbone:** `timm` `vit_small_patch16_dinov3.lvd1689m` (21.6 M params, 384-d — same
width as our GeoViT-small; 1 CLS + 4 register tokens; native 256 px; trained on
LVD-1689M natural images; DINOv3 license, research use). Downloaded via the timm HF mirror.

**IR → RGB-image mapping (fixed, documented):** z-scored band 3 → BT (K) with the shared
HAFS stats (272.14 ± 25.90; HAFS stores and IRAR cache use the same); IR-imagery convention
"cold = bright": v = clip((310 − BT) / 130, 0, 1); replicate to 3 channels; ImageNet
mean/std; bilinear 128 → 256 px (16×16 patches, 24 km each). Readouts: CLS and mean of
patch tokens (registers excluded).

**Scope:**
1. Generic frozen-embedder interface (`hafs_jepa/models/frozen_backbones.py`) used by
   `extract_seq_embeddings.py` and `irar_probe.py` (GeoViT checkpoint or timm model).
2. HAFS: per-frame embeddings → `dynamics_probe` (vmax sanity, Δvmax with track scalars).
3. IRAR: `irar_probe` → best-track vmax / Δvmax, per-category table.
4. Ablations if close: 128 px native input; CLS vs mean-patch; BT mapping range.
5. Later (separate decision): fine-tune DINOv3 on HAFS-IR (MAE or supervised) vs our
   from-scratch encoder — the "retrain from scratch?" question proper.

**Decision gate:** frozen DINOv3 vs frozen HAFS-IR MAE on (a) HAFS vmax and Δvmax,
(b) IRAR best-track vmax / per-category bias, with storm-bootstrap CIs.
→ **Answered 2026-10-02: DINOv3 wins on vmax in both domains, ties on Δvmax** (DONE.md).

**Follow-up: is it the objective or the data?** Between our runs and DINOv3, objective,
data scale/diversity (1.7 B natural images vs ~8 k HAFS sequences of strongly correlated
frames), teacher distillation (ViT-S is distilled from a 7 B teacher), augmentations and
compute all change at once. Disentangle in order of cost:
6. ✔ **Frozen natural-image grid (2026-10-02, DONE.md)** — objective dominates; scale adds
   ~0.01; DINOv2 rerun pending (input-size bug fixed). Original plan: — one factor at a time, all ViT, same
   probe: DINOv2 ViT-S/14 (142 M imgs) and DINO v1 ViT-S/16 (ImageNet-1k, 1.3 M) → data
   scale at a fixed objective family; supervised ViT-S/16 IN-1k and MAE ViT-B/16 IN-1k →
   objective at fixed data (MAE is ViT-B — a confound to state). Results under
   `results/irar_probe/{dinov2_vits14_224,dino_v1_vits16_224,sup_in1k_vits16_224,mae_in1k_vitb16_224}`.
6b. **JEPA-family and controlled-objective RGB models (queued 2026-10-02)** —
   OK-AI ViT-S/16 ImageNet-1k collection, *same codebase, data and 300-ep schedule* for
   **DINO, iBOT and LeJEPA** (community, Apache-2.0; loaded from the repo's own code in
   `/scale/scratch/qfebvre/venvs/foreign_backbones` via `scripts/embed_irar_external.py`,
   readout = mean patch token) → the cleanest objective comparison available, and LeJEPA
   is the SIGReg recipe this project's JEPA uses. Official **I-JEPA ViT-H/14 IN-1k**
   (timm, 632 M — size confound; ~5 h CPU). Results under
   `results/irar_probe/{okai_*_vits16_in1k,ijepa_vith14_in1k_224}`. Later: **V-JEPA 2**
   (video encoder, HF `facebook/vjepa2-vitl-fpc64-256`) fed the 8-frame 24 h clip directly —
   the only pretrained model with a native temporal input. No official LeJEPA weights exist.
7. **Adapt DINOv3 to HAFS-IR** (continued SSL at low LR, or the HAFS-IR MAE objective on a
   DINOv3 init) — does domain adaptation add on top of scale?
8. **DINO-family recipe from scratch on HAFS-IR (+ IRAR frames)** — the "exact recipe" test.
   Realistic target is DINOv2-style SSL for ViT-S (DINO + iBOT + KoLeo, EMA teacher,
   multi-crop), not the DINOv3 S model itself (distilled from a 7 B teacher, not trainable
   from scratch at that quality). Needs a physically screened augmentation set (no colour /
   contrast jitter on absolute BT — N2) and probably HAFS+IRAR to raise image diversity.
   Candidate implementation: `260324_jepa/stable-pretraining` (local; has DINO / DINOv2 ViT
   configs for ImageNet-100 in `benchmarks/imagenet100/` and `losses/dino.py`) or the official
   dinov3 training code with a custom dataset. GPU-days on the shared 2-GPU quota.
   **First run (cheapest, 2026-10-03 evidence):** IR frame-LeJEPA *with multi-crop local
   views* (`params.lejepa_local_views` 2–6, larger zoom range), random init — the grid shows
   LeJEPA = DINO on RGB and our IR frame-LeJEPA failed with 4 global, gently augmented views
   (invariance loss ~0.06 by ep 10). Augmentation search must stay physical (no BT jitter):
   local crops, scale, rotation, mirror, blur/noise, maybe random sub-band smoothing.
   *Launched 2026-10-03:* `scripts/run_ir_suite.sh train lejepa_mc` → `results/ir_lejepa_mc`
   (job 287475, 8 views = 2 global + 6 local; global zoom 1.0–1.6, local 1.8–4.0, ±24 px), probes
   chained by SLURM dependency (IRAR cls/gap, HAFS extraction → dynamics). Gate: real-IR
   vmax 24 h mean > MAE-HAFS 0.833 (and ≥ scattering floor 0.646 at minimum); watch the
   invariance loss — it must stay well above the ~0.06 plateau of the 4-global-view run.
   *Run 1 result (2026-10-04):* views harder but vmax 0.45 (GAP) ≈ BT-statistics floor →
   histogram shortcut (DONE.md). *Running:* `lejepa_mc_pj` (intensity jitter, job 353890) and
   `lejepa_mc_dino` (DINO v1 init, job 354054), probes chained. Decision: if jitter lifts
   vmax well above 0.5, the shortcut was the problem → combine jitter + pretrained init and
   then scale the recipe (lr / batch / epochs / projector to the LeJEPA paper); if the DINO-init
   arm stays ≥ frozen DINO v1 (0.856 / 0.893), HAFS-domain SSL is at least not destructive,
   and > means it helps.
   *Runs 2–3 (2026-10-06, DONE.md):* jitter fails; DINO-init ≈ frozen start. *Queued:* faithful
   MINIMAL.md recipe (`scripts/train_lejepa_faithful.py`, `results/lejepa_faithful/{scratch,dino_init}`,
   60 ep on HAFS-IR + IRAR ≤ 2022 frames) — then probe `checkpoints/epoch*.ckpt` with the CPU
   harness (`irar_probe pool=cls|gap`, `extract_seq_embeddings` → `dynamics_probe`).
   *Run 4 (2026-10-06, DONE.md): **the faithful recipe works from scratch** — HAFS vmax 0.855
   (+0.025 vs frozen DINOv3), IRAR 24 h mean 0.888 (+0.024); Δv24 tied. DINO-init arm scrambled
   by lr 2e-3 (worse at ep 20). Next: (a) HAFS-only ablation (job 508649) — does it hold without
   the 9 % IRAR frames?; (b) recipe ablations to find which ingredient mattered (lr/wd,
   projector, augmentation strength); (c) pretrained-init arm with low lr / layer decay;
   (d) the faithful recipe on temporal JEPA (the predictor objective) — now testable with a
   recipe that is known to learn; (e) use the new encoder in T9/T11 instead of DINOv3.
   *Ablations launched 2026-10-06* (`scripts/submit_lejepa_ablation.sh`; one factor changed vs
   `scratch`, same corpus / 60 ep; probes chained: IRAR CLS + HAFS dynamics on `last`):
   `abl_bs64` (bs 256 → 64 = failed runs' batch; user's bet), `abl_tiny` (ViT-Tiny, 192-d),
   `abl_nobright` (no brightness jitter, contrast kept), `abl_oldopt` (lr 1e-4 / wd 1e-3),
   `abl_lamb09` (λ = 0.9; launched as "≈ failed runs" — wrong, they had λ_eff ≈ 0.1–0.15),
   `abl_smallproj` (projector
   384-384-128), `abl_mildcrop` (crop area ≥ 0.4 ≈ failed runs' zoom 1–1.6); plus
   `scratch_hafs_only`. Reference = `scratch` (HAFS vmax 0.855, IRAR 24 h mean 0.888).
   Note bs 64 at fixed epochs = 4× more steps; if it fails, also try bs 64 + lr 5e-4.
   *Result 2026-10-07 (DONE.md):* only λ breaks it (λ 0.9 → 0.35); bs/optimiser/projector/corpus/
   init ≈ no effect; mild crops −0.01–0.03; no brightness +0.012 on real IR. *Queued:*
   `abl_lamb01`, `abl_lamb025` (bracket the failed runs' effective λ), `abl_nophoto`. If λ 0.1
   still works, the failed runs' remaining differences are the batch-centering loss and the
   multi-crop / temporal view design — test the centering loss next.
   *λ result 2026-10-07:* 0.1 works (−0.02), 0.25 degrades (−0.10), 0.9 collapses.
   *Temporal arms launched 2026-10-07* (step (d); `train_lejepa_faithful.py --mode tviews|tjepa`,
   HAFS 43-step blocks of the corpus, steps matched to `scratch` (1340/epoch × 60), λ = 0.02,
   same augmentations; probes chained): `tviews_{scratch,init}` (views 2–3 from ±3–6 h),
   `tjepa_{scratch,init}` (8 ctx frames → predictor → embeddings at +3…+24 h, 4 sampled leads,
   bs 128 sequences × 12 frames, no stop-grad/EMA); `_init` = encoder from `scratch/last`
   (lr 2e-3 as before — may scramble it like `dino_init`). Gate: Δv24 / Δv48 vs `scratch`
   (the temporal objective must earn its keep on intensity *change*), vmax not worse.
   *Failure bisection launched 2026-10-07* (user-approved). Reading the Lightning frame step
   (`_lejepa_frame_step`) shows the batch-centering loss is **not** applied there (temporal step
   only) → dropped as a suspect. Exact failed `lejepa_mc` config (run.lock): loss `inv + 0.09·SIGReg`
   with SIGReg **pooled over all B·V = 512 embeddings** (statistic ×512, 1024 slices); projector
   Linear(384,128)-GELU-Linear(128,128) **without BN**; views = `FrameViewAugment` 2 global (rot 180°,
   zoom 1–1.6, ±4 px) + 6 local (zoom 1.8–4, ±24 px), mirror/blur 0.5, pixel noise 0.05, no
   photometric; bs 64, lr 1e-4, wd 1e-3, 10-ep warm-up, **26.9 k steps** (vs 80 k); HAFS only.
   Its invariance loss sat at 0.58–0.61 from epoch 5 — the λ = 0.9 signature.
   The faithful trainer now reproduces it (`--views mc --proj lightning --sig_pooled --sig_weight
   --n_slices`, reusing the Lightning `FrameViewAugment` class). Arms (HAFS-only corpus; reference
   `scratch_hafs_only`): `rep_failed` (all failed settings) and `rep_fix_{loss,proj,views,opt}` (one
   group restored to faithful; `opt` = bs 256 / lr 2e-3 / wd 5e-2 / 80 k steps); single factors on
   the working recipe: `abl_lightproj` (BN-less 128-d projector), `abl_pooledsig` (pooled ×V·B
   SIGReg, 1024 slices — note pooling also raises the effective SIGReg weight ≈ 4×).
   Reading: if `rep_failed` fails and exactly one `rep_fix_*` recovers, that group is the cause;
   if `rep_failed` *works*, the failure is in the Lightning code path (compare implementations on
   identical batches).
   *2026-10-08 (user: "queue 2 and 4"):* bisection resubmitted (first submission died on a zsh
   arg-splitting slip, `${=B}`). **Step 2 — best encoder:** `nophoto_ep120` (best recipe λ 0.02 +
   strong crops + no brightness/contrast, 120 ep) for headroom; T9 imagery-only and T11 HAFS+IR
   re-run with the `abl_nophoto` embeddings instead of DINOv3 (`--tag _LEJEPA`; entries
   `2023_IR_RT_LEJEPA*`, `2023_HAFS_*_LEJEPA*`, `results/tcbench_hafs_ir_lejepa.md`).
   **Step 4 — T7 4a control:** `irar_only_nophoto` (same recipe, IRAR ≤ 2022 frames only, 31.7 k,
   steps matched = 80 k by wrapping) vs `abl_nophoto` (HAFS + IRAR) and `scratch_hafs_only`:
   is synthetic HAFS needed at all, and does real-only pretraining transfer back to HAFS?
   *Results 2026-10-09 (DONE.md):* failure = pooled SIGReg × BN-less projector (bisection closed);
   120 ep ≈ 60 ep; IRAR-only < HAFS+IRAR on both domains. Follow-up: fix `_lejepa_frame_step`
   (per-view SIGReg, λ form, BN projector) or retire it in favour of `train_lejepa_faithful.py`.
   *Lightning fix done 2026-10-09 (user):* opt-in `train.lit_module.lejepa_loss=faithful`
   (+ `lejepa_lambda`), `params.sigreg_proj_kind=mlp_bn` (`models/projectors.py`); defaults
   unchanged (old checkpoints load). Validation arm `scripts/run_ir_suite.sh train
   lejepa_mc_fixed` = failed `lejepa_mc` + the two fixes (job 799581; probes 799686–88). Gate:
   IRAR 24 h mean ≳ 0.80 (rep_fix level) vs 0.45 for `lejepa_mc`.
   **Gate passed 2026-10-09:** IRAR 24 h mean 0.868 (vs 0.394 CLS for `lejepa_mc`). T10 closed
   apart from the pending HAFS dynamics probe of this arm.
   **Design (2026-10-02, user): every recipe tested with and without the best pretrained
   init.** Same architecture for both arms so only the init differs — timm
   `vit_small_patch16_dinov3` (RoPE, 4 registers, 384-d), or the OK-AI LeJEPA ViT-S/16 when
   the recipe is LeJEPA (same objective as its pretraining) — same recipe, data, budget and
   probes:
   - arm A — random init (does the recipe learn from HAFS alone?);
   - arm B — init from DINOv3 LVD-1.7B weights (does HAFS-domain SSL add on top of scale?);
   - reference — frozen DINOv3, no training (the bar both arms must clear).
   Arm B risks drifting away from the pretrained features (forgetting); run it at low LR /
   short schedule and log the HAFS + IRAR probes during training so the best checkpoint is
   chosen on probes, not on the SSL loss. Applies equally to the MAE recipe (MAE-on-HAFS
   from DINOv3 init) so objective × init is a 2 × 2.

### T11 — Do observation embeddings add information to the HAFS forecast? (IR now, wind obs next)

- **Accepted:** 2026-10-06 (user). Status: IR part done (DONE.md 2026-10-06: MOS gives most
  of the gain; IR intensity −0.4–0.6 kt at 6–24 h; embedding −0.3–0.6 kt at 30–72 h only via
  the large-data stacked forecaster; RI n.s.). Wind-observation part **recorded, not started**.
  IR follow-ups: swap DINOv3 for the faithful-LeJEPA encoder; add the stacked entries to
  `tcbench_compare.py` / `tcbench_ri.py`; validate the MOS on a season hold-out (train 2024 →
  test 2023) to bound the in-season bias-learning optimism.
- **Question:** given the HAFS forecast, does an embedding of *observations at t0* improve
  intensity and RI? Statistical post-processing (MOS / SHIPS-style residual correction of
  HAFS vmax/pmin per lead; pooled RI classifier), with the feature set grown one block at
  a time so each block's contribution is a paired Δ:
  HAFS raw → HAFS-MOS (HAFS predictors only) → + IR-estimated intensity/trend → + IR
  embedding PCA blocks.  No best-track input at t0 (HAFS analysis + imagery only).
  Data limit: HAFS forecasts 2023–26 × IRAR ≤ 2024 → storm-grouped CV over 2023–24 cases,
  scored on TCBench 2023 00/12Z.  The MOS arm is the control that matters: any gain of
  "+IR" over raw HAFS that MOS alone also gets is bias correction, not image information.
- **Wind-observation arm (next):** add an embedding of observed surface wind at t0 (latest
  pass within ±6–12 h, plus an availability flag and coverage fraction).  Sources to check:
  SAR (Sentinel-1/RCM via cyclobs, `projects/cyclobs_offline`, `2509_sar_ml`), MAXSS
  multi-sensor TC winds (SMAP/SMOS/AMSR2/ASCAT/SAR; `250930_maxss_era5pp`, `maxss-ml`),
  scatterometer vectors.  Encoder options: our HAFS wind encoder (u10/v10, but radiometers
  give speed only → speed-only variant needed), or frozen DINOv3 on a speed image as for IR.
  Issues to settle first: sparse/irregular sampling (most inits have no pass within 6 h —
  measure the hit rate on 2023–24 first; that alone may decide it), partial swath coverage
  of the core, and sensor saturation above ~50 m/s (C-band co-pol; SMAP/SAR cross-pol fine).
  Expected value is in structure (RMW, r34, symmetry) more than vmax → also score radii.
- **Related cheap arm:** embeddings of HAFS's *own* forecast fields (sat IR and wind at
  lead L, from the HAFS zarrs) as predictors — tests whether the model's fields carry
  information its tracker vmax discards (no observation needed, full coverage).
- **Gate:** "+block" beats the previous arm on intensity MAE or RI CSI with a storm-bootstrap
  CI excluding 0 on the 2023–24 OOF cases.

### T12 — Next round (2026-10-09, user): intensity change, 256 px, microwave

- **Accepted:** 2026-10-09 (user: "1. 48–72 h of context + fine-tuning, 2 and 3").
- **1a. Longer context (frozen):** `scripts/context_length_probe.py` — IRAR, same anchors (full
  72 h history) for GRU over 24 / 48 / 72 h of embeddings, vs short and *long* best-track scalar
  baselines (33/45/69 h trends), Δv24 / Δv48 / vmax; LeJEPA-nophoto and DINOv3 embeddings
  (`results/context_length/{lejepa_nophoto,dinov3}`, jobs 805628/9). Gate: GRU 72 h + long
  scalars beats scalars long and GRU 24 h on Δv (storm bootstrap).
  **Done 2026-10-09 — gate failed** (48/72 h ≈ 24 h on Δv24/Δv48, CIs straddle 0; vmax +0.006);
  see DONE.md.
- **1b. Fine-tuning on Δv:** `scripts/finetune_dv.py` (+ `run_finetune_dv.sh`) — encoder from
  `abl_nophoto`, per-frame CLS → GRU + scalars → (Δv24, Δv48); `--enc_lr 0` frozen control with
  the identical head/augmentation; K = 8 and 16 (`results/finetune_dv/{frozen,ft}_k{8,16}`,
  jobs 806929–32). Gate: ft − frozen ΔR² on Δv24 test (2023–24) with CI excluding 0.
  **Done 2026-10-10 — gate failed** (K 8 +0.015 [−0.027, +0.057], K 16 +0.012 [−0.012, +0.033]);
  see DONE.md.
- **2. Native 256 px (IDEAS I10):** `scripts/build_slim256_ir.py` (HAFS IR 256 px store mirroring
  the 128 scratch, done: 7243 train / 733 val seqs), IRAR cache at 256 (`build_irar_cache
  out_px=256`, verified: 2×2 means reproduce the 128 cache to 1e-6), corpus → `nophoto_256`
  (best recipe at 256) with IRAR-256 and HAFS-256 probes (jobs 806946–50). Reference
  `abl_nophoto` (same recipe at 128). Caveat: IRAR source ≈ 4 km, so real-IR gain is bounded.
  **Done 2026-10-10:** HAFS vmax +0.021\* (Ridge), IRAR ≈ 0, Δv n.s. → not adopted as default
  (DONE.md).
- **3. Microwave (SSMIS 37H/37V/91V/91H, zarr idx 4–7):** 4-channel HAFS corpus (`build_frame_corpus
  band_pos=[4,5,6,7] irar_cache=""`), `mw4_zspace` (trainer `--zspace`: crops/flip/blur in z-units,
  no IR brightness map/solarize; 66 ep = matched steps) + matched IR control `ir_zspace_hafs`
  (same augmentation, HAFS-only IR); HAFS dynamics probes (jobs 806933–39). Next if MW is
  competitive: TC-PRIMED transfer (the real MW counterpart; `tcprimed_adapter` exists in the module).
  **Done 2026-10-10:** MW4 vs IR: Δv24 GRU +0.136\*, single-frame Δv and vmax n.s. → MW is
  competitive on simulated HAFS; real confirmation = TC-PRIMED (T13 C).  T12 closed.

### T13 — MoTiF-style multi-source evaluation (2026-10-09, user)

- **Accepted:** 2026-10-09 (user: "include or adapt the evaluation approach of MoTiF").
- **Reference:** Dauvilliers & Monteleoni 2025, *MoTiF*, Environmental Data Science 4 e36
  (doi 10.1017/eds.2025.10014); follow-up *MotifGen* arXiv 2606.24263 (IR + PMW, CRPS).
- **Their protocol (read from the PDF, not the web summary):** TC-PRIMED; split 80/15/15 *by storm
  ID* (all years mixed); inputs = every source in [t0 − 24 h, t0] (≤ 1 obs per PMW sensor + 1 ERA5
  state); tasks (fine-tuned): (a) ERA5 surface fields at t0 + 24 h — RMSE per variable (u10, v10,
  10 m wind speed, mean SLP, min SLP) within 1000 km of the centre + storm-centre error (km) from a
  predicted distance-to-centre channel, ERA5 randomly cropped 60–100 % so the storm is not centred;
  (b) MSW at t0 + 24 h — RMSE / MAE kt (PMW only 23.07 / 17.37, ERA5 only 19.54 / 14.39,
  ERA5 + PMW 17.28 / 12.51) + per-sample |error| box plots (medians); (c) masked-PMW reconstruction
  (qualitative).  Every task is reported as a **source-ablation table** (no fine-tune / each source
  alone / all).  No persistence or climatology baseline, no confidence intervals.
- **Adaptation (ours = frozen embeddings + light heads, storm bootstrap CIs, persistence and
  track-scalar baselines always in the table):**
  - **A. HAFS source-ablation forecast (cheap, embeddings mostly exist):** inputs over the 8 leads
    [L − 24 h, L] of a forecast; sources = IR, WV (ABI 0–2), MW (4–7), wind(L) (u10/v10 encoder),
    track scalars; targets at L + 24 h: vmax, min SLP, wind field (u, v, speed) via EOF
    regression (top-k EOFs from train, reconstruct, RMSE over the disc), r34 quadrants.
    Sat and wind scratch share `storm`/`init_time_idx`/`init_time` (checked 2026-10-09) → join on
    `init_time`.  Uses the T14 encoders.
  - **B. Localisation error:** random-shift the input (as their random crop) and regress the centre
    offset from the frozen embedding → km error; IRAR and HAFS.
  - **C. TC-PRIMED replication (real IR + PMW):** local copy
    `/scale/project/ifremer-isi-jumeaunumerique/TC_PRIMED_DATASET/v01r01/final` (1987–2024,
    1.7 TB).  Each overpass `.nc` holds the PMW swath (+ GPROF), a collocated **IRWIN** image
    (480 × 640) and `overpass_storm_metadata/intensity_change*` (9 periods) → real IR + MW pairs.
    Run MSW + 24 h with their storm-ID split (comparable to 17.37 / 14.39 / 12.51 kt) **and** our
    season hold-out (train ≤ 2022, test 2023–24); source ablation IR / PMW 37 / PMW 89 / IR + PMW.
  - **D. (ours, they do not quantify) missing / stale sources:** error vs time since the last PMW
    pass and vs number of sources available.
- **Next:** build a TC-PRIMED overpass cache (PMW 37/89 GHz + IRWIN regridded storm-centred at the
  HAFS geometry), then C; A once the T14 embeddings exist.
- **Started 2026-10-10:**
  - *C cache* — `hafs_jepa.data.tcprimed` + `scripts/build_tcprimed_cache.py`: conical imagers
    only (SSMIS, SSMI, TMI, GMI, AMSR-E, AMSR2; ATMS/MHS lack 37/89 dual-pol), IR + 37H/37V/91V/91H
    (= HAFS zarr idx 3–7, z-scored with HAFS stats), 128 px × 6 km, packed validity masks,
    labels incl. `dv{m24…p24}h`.  Visually checked on one file per instrument (IR cold cloud ↔
    89 GHz scattering aligned; x ↔ lon, y ↔ lat r = 0.999).  Array 1002086 (1987–2024) →
    `/scale/scratch/qfebvre/tcprimed_cache/{year}/`.  **Done 2026-10-11** (130 083 overpasses, 0
    errors; DONE.md).  Embedding (`scripts/embed_tcprimed.py`, 2026-10-11): `bs_shared8_cont` ×
    bands 3/4/5/6/7 (1088489–93), `mw4_zspace` (1088494), `ir_zspace_hafs` (1088495),
    `abl_nophoto` (1088496) → `results/tcprimed/emb/`.  Next: embed with frozen `bs_shared8`
    (per band), `mw4_zspace`, IR specialist; probes MSW now / +24 h, storm-ID and season splits.
    **Done 2026-10-12** (`scripts/tcprimed_probe.py`, DONE.md): zero-shot transfer works; IR + MW
    best; shared ≫ multi-channel on real PMW; no frequency penalty.  Open: D (staleness — needs a
    multi-overpass model), zero-shot unseen bands (19 / 23.8 / 150–183 GHz), matched MoTiF sample
    list, and mixing TC-PRIMED training storms into the shared corpus (as IRAR did for IR).
    **Unseen bands done 2026-10-13** (`tcprimed_unseen_probe.py`, DONE.md): zero-shot transfer follows
    the physics family.  Remaining open: D (staleness), matched MoTiF, TC-PRIMED mixing (next).
  - *TC-PRIMED mixing (2026-10-13, user step 6)* — `scripts/build_mixed_corpus.py`: 1-channel
    (frame, band) corpus = HAFS all-8 × 8 bands (2.49 M) + seen-band TC-PRIMED images (365 k, ≥ 80 %
    covered, seasons ≤ 2022, storm-split test storms excluded, unseen bands excluded) → 12.8 % real
    (`/scale/scratch/qfebvre/lejepa_frames_mix_tcp`).  `scripts/submit_mix_tcp.sh`: train `mix_tcp`
    (1 216 steps × 60 ep = `bs_shared8` compute; 1311013) → TC-PRIMED embeddings (5 seen + 6 unseen)
    → `run_tcprimed_probes.sh mix_tcp` (1311025); HAFS b3/b5 dynamics + IRAR (1311026–30).
    Control = `bs_shared8` ep 60: embeddings 1310968–78, probes 1310987 (`prefix=shared8`).
    Gate: real-data probes (season and storm splits) above control with CI excl. 0, HAFS not worse.
  - *A, first pass (satellite sources only)* — `dynamics_probe targets=` gains L + 24 h state
    targets (`vmax_24h_kt`, `mslp_24h_mb`, `r34_24h_nm` (quadrant mean), `rmw_24h_nm`; scalars
    include current r34 for the r34 target).  `run_source_ablation.sh` = subsets of the shared
    8-band encoder (IR / WV 0–2 / MW 4–7 / MW 37 / MW 91 / IR+WV / IR+MW / WV+MW / all), PCA-128 late
    fusion, CLS, 3 GRU reps: jobs 1002233–41 → `results/dynamics_probe/source_ablation/`.
    **Done 2026-10-11:** MW carries all dynamic / structure skill; IR, WV redundant given MW (DONE.md).
    Smoke test (shared b3, static models): image+scalars GBM over scalars +0.035–0.048 on all
    four L + 24 h targets.  Not yet: wind source (no working-recipe wind encoder / seq
    embeddings), wind-field EOF targets (need wind zarr reads).
  - *Wind arm (2026-10-11, user: "what Δv24 is deducible from wind-speed history")* —
    speed-only LeJEPA (`hafs_jepa.data.wind_speed`: |(u10, v10)| z-scored, mean 9.685 / std
    5.342 m/s; speed is flip-invariant and matches speed-only observations, T11).  **The wind
    store's val storms differ from the sat store's** (4 of 45 common; 42 sat-val storms sit in
    wind train) → everything re-split on the sat split: corpus = wind sequences of non-sat-val
    storms (`build_frame_corpus exclude_storms_from=`), embeddings grouped by sat-split storms
    (`extract_seq_embeddings split_storms_from=`), comparisons on the 712 / 733 sat-val sequences
    with wind (`concat_seq_embeddings align=true align_with=`; `dynamics_probe expect_val=0`).
    Floor (IDEAS I7, extended): `scripts/wind_profile_features.py` — 48-ring azimuthal-mean
    profile + quadrant maxima in 4 radial bands + max/p50/p90/p99 (68 features).
    `scripts/submit_wind_lejepa.sh`: corpus 1089390 → train 1089391 (60 ep, z-space views) → seq
    1089392; feats 1089393; aligned arms (`run_wind_ablation.sh`, CLS, 3 GRU reps) wind_feats /
    wind / ir / mw / all8 / wind_feats+mw / wind+mw / wind+all8 = 1089394–401 →
    `results/dynamics_probe/wind_ablation/`.  Note: HAFS vmax is derived from HAFS's own 10 m wind,
    so static vmax from wind is near-trivial — Δv and the +24 h targets are what count.
    *2026-10-13:* wind training + embeddings done (1089391 / 1089392, final loss inv 0.0284).  First
    ablation round (1089394–401) **discarded**: single-source wind arms were not restricted to the
    sat-aligned sequences (881 vs 712 val), and aligned arms kept the first source's row order, so
    predictions could not be paired.  Fixed (`concat_seq_embeddings` align → canonical sorted order;
    `dynamics_probe` parquet now carries `init_time` + `lead`; every arm aligned with both wind and
    sat sets) and rerun: 1303286–93.

### T14 — One SSL model for all frequencies vs band-specific vs multi-channel (2026-10-09, user)

- **CLOSED 2026-10-13** — answered on HAFS (2026-10-10/11) and on real TC-PRIMED PMW (2026-10-12):
  one shared single-band encoder + per-band late fusion, no band-ID token.  Leave-one-band-out
  (below) continues as its follow-up.
- **Accepted:** 2026-10-09.
- **Setup:** faithful LeJEPA, z-space views (`--zspace`), HAFS-only 8-band 128 px corpus
  `/scale/scratch/qfebvre/lejepa_frames_all8` (job 863755; same frames and steps for every arm).
  Trainer: `--chans` (channel subset), `--band_mode shared` (one 1-channel encoder, random band per
  sample), `--band_embed 1` (learned per-band patch-token embedding, zero-init; probes pass the
  zarr band via `frozen_backbones.build_embedder(band=)`).  Launcher `scripts/submit_band_study.sh`.
- **Arms** (train → seq embeddings per eval band set → HAFS dynamics probe; IRAR probe on [3]):
  | arm | input | jobs (train / seq / dyn) |
  |---|---|---|
  | `bs_wv62` | specialist ABI 6.2 µm (0) | 866659 / 866660 / 866661 |
  | `ir_zspace_hafs` (T12) | specialist ABI 10.3 µm (3) | 806936 / 806938 / 806939 |
  | `bs_37v` | specialist 37V (5) | 866662 / 866663 / 866664 |
  | `bs_91v` | specialist 91V (6) | 866665 / 866666 / 866667 |
  | `bs_abi4` | multi-channel ABI 0–3 | 866668 / 866669 / 866670 |
  | `mw4_zspace` (T12) | multi-channel MW 4–7 | 806933 / 806934 / 806935 |
  | `bs_all8` | multi-channel 0–7 | 866671 / 866672 / 866673 |
  | `bs_shared8_emb` | shared, band embedding; eval 0 / 3 / 5 / 6 | 866674 / 866675… / …866683, IRAR 866679 |
  | `bs_shared8` | shared, no band embedding (the old `random_single` failure mode, now with the working loss) | 866684 / … / …866693, IRAR 866689 |
- **Questions / gates:** (1) per band, shared vs specialist (negative transfer?) — matrix rows =
  models, cols = eval band, vmax / Δv24 R² with storm bootstrap; (2) multi-channel vs late fusion
  of shared per-band embeddings (concat) on the same band sets; (3) does the band embedding matter;
  (4) IRAR transfer of the shared model (band 3) vs IR specialist.
- **Caveat:** specialists each get the full step budget for one band (8× the per-band compute of
  the shared model) — shared parity at equal total compute is the favourable outcome.
- **Status 2026-10-10 (DONE.md):** Q1 shared ≈ specialist (vmax −0.01 to −0.017, Δv ≈) at ⅛
  per-band compute; Q3 band embedding hurts → drop; Q4 shared transfers to IRAR like the IR
  specialist (better Δv GRU, below `abl_nophoto` on vmax); MW inputs carry the HAFS Δv24 GRU gain.
  **Open: Q2** late fusion (concat of `bs_shared8` per-band seq embeddings on bands 0/3/5/6 vs
  `bs_all8`) — CPU-only, embeddings exist.
- **Status 2026-10-11 — all follow-ups done (DONE.md 2026-10-11):** MW gain confirmed over 15 GRU
  seeds; Q2 answered (late fusion of the shared model ≥ multi-channel); 60 epochs ≈ converged.
  T14 can close once the TC-PRIMED transfer (T13 C) has been read.
- **Next (agreed 2026-10-11, after the wind arm): leave-one-band-out shared models** — train the
  shared encoder on 7 bands, probe the 8th: hold out 37V (sibling 37H seen), WV 6.9 (neighbours
  seen), IR 10.3 (no sibling).  Clean unseen-band test with HAFS labels; ~2.5 h GPU each.
  Queued 2026-10-13 (`submit_band_study.sh bs_lobo_{37v,wv69,ir}`, `--chans` subsets); first
  submission OOM at 120 G (channel subset copies 71 GB) → resubmitted with 220 G: 1310906 / 09 / 12
  (+ seq / dyn / IRAR chains); reference `bs_shared8` b1 dynamics probe 1307021 (done).
- **Queued 2026-10-10 (user: "proceed with 1–5 + shared-model continuation"):**
  - *GRU seed check* — `dynamics_probe gru_reps=5` (new option: independent 3-seed GRU ensembles
    with different early-stopping holdouts) on IR / WV / 37V / 91V / ABI4 / MW4 / all8 /
    shared b3, b5 / `abl_nophoto` (CLS) + IR, all8 (GAP): jobs 1001846–57 →
    `results/dynamics_probe/gru_reps/`.  Gate for the MW claim: MW − IR Δv24 GRU > 0 in every rep.
  - *Q2 late fusion* — `scripts/concat_seq_embeddings.py` (PCA-128 per source, concat) +
    `run_fusion_probe.sh`: specialists 0/3/5/6 (1001977), shared 0/3/5/6 (1001978), shared all 8
    (1001979; needs shared b1/b2/b4/b7 seq embeddings 1001791/93/94/95) vs `bs_all8`.
  - *Continuation* `bs_shared8_cont` — encoder init from `bs_shared8/last` (the trainer saves no
    projector/optimizer → warm restart: new projector, lr 1e-3, 2 warm-up epochs), +60 epochs
    (120 total): train 1001781 (GPU, waits on QOS) → seq/dyn [0] [3] [5] [6] + IRAR.  Learning
    curve point at epoch 30 of `bs_shared8`: seq/dyn b3 1001796/97, b5 1001798/99, IRAR 1001800.
    Question: are 60 epochs enough to digest 8 bands (each band sees ⅛ of the steps)?
- **Later if shared wins:** channel-token model (ChannelViT/SatMAE-style: per-band tokens + band
  embedding, joint attention, band dropout) → any band subset, missing-pass robust; then on
  TC-PRIMED real IR + PMW (T13 C).

### T15 — Hierarchical k-means sampling, revisited on the working recipe (2026-10-09, user)

- **Accepted:** 2026-10-09.  History: the old `HierarchicalResamplingCallback` (Lightning/WebDataset,
  per-**storm** rejection weights, `sat_qw`) was only ever run together with centroid invariance
  on the failing recipe — never isolated.
- **Implementation:** `src/hafs_jepa/training/frame_kmeans.py` (per-**frame**, Vo et al. 2024 balanced
  hierarchical sampling: mass uniform over L1 clusters → leaves → frames; per-frame weight capped at
  `max_rep` = 5 × uniform; cosine geometry), `scripts/cluster_frame_corpus.py` (embed corpus with a
  checkpoint → `weights.npy`, `labels.npy`, `emb.npy`, `stats.json` with ESS and mass per source),
  trainer `--sample_weights` (each epoch draws steps × bs frames ∝ w, with replacement) and
  `--cluster_every E` (online re-clustering of the current encoder; not queued yet).
- **Arm `kmeans_nophoto`:** = `abl_nophoto` (60 ep, same steps) + weights from `abl_nophoto`'s own
  embeddings, k 50 × 5.  Jobs: cluster 896766 (CPU) → train 896767 → IRAR 896768, seq 896769,
  dyn 896770.  Reference `abl_nophoto` (IRAR 0.859/0.902/0.927, HAFS 0.866/0.920).
- **Gate:** IRAR and HAFS vmax / Δv24 within or above `abl_nophoto` CI; check `stats.json`
  (mass per source, ESS) first — if leaves are dominated by IRAR or by featureless frames, the
  balancing is a distribution shift, not curation.
- **Done 2026-10-10 — no effect** (IRAR / HAFS vmax and Δv24 within CI; IRAR Δv48 −0.029\*);
  DONE.md.  Online variant not queued.  **CLOSED 2026-10-10** (user).
- **Next if positive:** online variant (`--cluster_every 10`, from scratch) and a mix sweep
  (`--cluster_mix 0.5`).

### Superseded wind artifact cleanup (deferred from T8)

The corrected reader and shard restoration are complete; retain historical artifacts
for reproducibility until no run needs them. Optional cleanup remains: delete or
rename `webds/slim128/surfwinds` (superseded by `webds/slim128_wind_v2`) and
`HAFS/.hafs_jepa_init_time_wind.json.pre_repair`. No deletion was performed.

## Promotion template

### T\<number\> — Title

- **Accepted:** YYYY-MM-DD
- **Origin:** `IDEAS.md` section

**Goal:**

**Accepted scope:**

**Non-goals:**

**Compatibility considerations:**

**Validation:**

**Completion criteria:**
