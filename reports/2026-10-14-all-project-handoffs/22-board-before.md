# TODO

Accepted implementation scope only. Promote an item from [IDEAS.md](IDEAS.md)
after its workflow, constraints, contract effects, and validation plan have
been agreed. Record completion and durable decisions in [DONE.md](DONE.md) with
a date.

Scope note: direct S1/S2/S3 processing and evaluation now exist. Historical
S2-only conclusions retain their original scope; October common-model results
are explicitly scored on each mode. See [STATUS.md](STATUS.md) for current status.

## Active

### T6 — Corrected-denoised comparison and validation follow-through

- **Accepted:** 2026-10-08; NESZ correction confirmed by user 2026-10-09
- **Status reviewed:** 2026-10-10

**Completed:** WW3 best-estimate refresh reconciled 146,104/146,104 grids with
zero extraction failures; rebuilt wave datasets; 144 wind-only and 144 joint
wind/wave incidence fits; 48 common S1/S2/S3 wind models at 5k/15k total
acquisitions; full-archive empirical noise-floor extraction; corrected xsar
NESZ and NEGZ to square the amplitude-valued denoising LUT. Completed evidence
and metrics are recorded in [DONE.md](DONE.md) and [STATUS.md](STATUS.md).

**Completed follow-through 2026-10-13:** all 35,594 corrected-denoised
products, paired datasets, 192 raw/denoised fits and within-acquisition metrics
are complete. The report job wrote CSVs; readable Markdown and PNG/PDF reports
were added on October 13. Corrected denoising generally increases retrieval
error and reduces within-acquisition correlation. Keep raw as the current
retrieval benchmark; the confirmed noise formula remains corrected.
[Report](../biomass_proc/analysis/denoised_20261010/REPORT.md).

**Remaining:** finish original refreshed wave dataset provenance: those
manifests still record embedding version `unresolved`. The paired calibration
datasets now pin encoder/config checksums and source manifests. Potential
clipping/error diagnostics are a recommended follow-up, not a submitted job.
T5 still requires scientifically useful within-acquisition retrieval skill;
this campaign did not resolve that limitation.

**Coverage limit:** the refresh covers processed SAR through September 4, not
all acquisitions through today. Best-estimate source availability alone does
not imply valid ocean targets: CWAVE has 532,925 finite hs tiles out of 851,942
source tiles. Source exclusions and missing targets remain explicit.

**Progress 2026-10-10:** 12 representative corrected-denoised checks passed.
Feature production for the frozen 35,594-acquisition comparison set is submitted
as 1003161; paired datasets 1003248, raw/denoised fits 1003397 and report 1003675
are chained after successful prerequisites. Incidence is fixed in both arms;
training products and common finite tiles are paired. Some representative
products remain almost fully clipped and are explicitly tracked. No denoised
performance conclusion is available yet. [Campaign details](../biomass_proc/analysis/denoised_20261010/README.md).

Saved incidence/common-model within-acquisition assessment completed (1002068).
Common 15k + incidence embedding mean scene correlations are S1/S2/S3
0.268/0.237/0.252, versus separate 5k without incidence 0.231/0.207/0.232.
Negative scene correlations remain 27–30%; T5 remains open.
Completed job IDs and output contracts are in
[`resume_20261008/README.md`](../biomass_proc/analysis/resume_20261008/README.md).

### T1 — Generalize and process S1 and S3 DGM products

- **Accepted:** 2026-08-31
- **Priority:** next data-production task
- **Origin:** processing-scope audit in [DONE.md](DONE.md)

**Goal:** extend the S2-only pipeline to process the 9,267 S1 and 12,545 S3 DGM
products in the 2026 archive without mixing modes or overwriting S2 artifacts.

**Accepted scope:** replace the hard-coded S2 discovery glob with an explicit
mode selector; verify the BIOMASS reader and every stage on representative S1
and S3 products; define mode-partitioned L1B/L1C, embedding, zero-shot,
collocation, run, and analysis roots; run small smoke subsets before full Slurm
sweeps; produce per-mode source/success/failure manifests and failure reasons.

**Non-goals:** treating a successful file write as model-transfer validation;
pooling modes before their sampling geometry and feature distributions have
been audited; silently changing the existing S2 benchmark.

**Compatibility considerations:** preserve the current S2 path and product
selection as a reproducible default or named configuration. Product mode must
be an explicit catalogue/dataset column and part of cache and run identities.

**Validation:** one end-to-end S1 and S3 product first, then stratified samples
covering acquisition geometry and polarization availability; schema/dimension
comparison against S2; archive-to-output reconciliation for each stage.

**Completion criteria:** isolated S1 and S3 full-archive runs have manifests,
stage counts, documented exclusions, and collocated outputs suitable for
scientific evaluation.

**Progress 2026-08-31:** generalized discovery and isolated mode run state are
implemented. The 21,813-product raw-sigma0 campaign is active as Slurm
controller `3579404`; CWAVE array `3579405` feeds the first stage. Completion,
failure reconciliation, and downstream stage counts remain open.

**Progress 2026-09-04:** controller `3579404` completed all four stage barriers,
and reconciliation controller `3654497` incorporated the 991 S3 acquisitions
that arrived after the original snapshot. Against the current 9,267 S1 and
13,537 S3 source directories, final S1/S3 counts are respectively: CWAVE
L1B+L1C 9,260/13,537, collocated embeddings 9,239/13,335, and collocated
zero-shot products 9,253/13,495. The product-level manifest and 230-row residual
exclusion queue are under `biomass_proc/analysis/s1_s3_audit/`. Discovery now
rejects transfer remnants such as `*.tmp.zip`.

**Progress 2026-09-05:** all 230 residuals are attributed by
`analysis/classify_s1_s3_failures.py` (230/230, none unattributed). 166 are a
producer bug — `_is_wv` used a substring test that misroutes any BIOMASS name
whose random trailing token contains `WV` into the Sentinel-1 wave-mode reader.
The same bug also costs 42 S2 products, so the S2 benchmark is affected;
208 products are recoverable in total. The producer sources are fixed and
covered by `tests/test_producer_wv_routing.py`. The remaining 64 are genuine
exclusions or transient: 49 invalid footprint geometry, 4 unreadable
measurement files, 3 missing inputs, and 8 lost to a worker-environment
failure. See [DONE.md](DONE.md), 2026-09-05.

**Progress 2026-09-05 (recovery):** `OceanSarEmbedOnnx` v3 is registered with
`@raw` moved to it (weights byte-identical to v2), and controller `3657544`
reran `embed` and `colloc` for all 208 products, 26/26 chunks each with no
failures. All 208 are recovered — S2 now has 42 more products than the
benchmark was built on. 64 genuine failures remain, plus 178 S3 acquisitions
that arrived during the run and are reported as `not_yet_processed`.

**Progress 2026-09-05 (snapshot cleanup):** the backlog had grown to 227 S3
acquisitions, so the cleanup list was frozen as
`analysis/s1_s3_audit/snapshot_20260905_cleanup_paths.txt` (227 backlog + the 8
retryable chunk-environment failures = 235) before processing. Controller
`3659534` ran all four stages, 30/30 chunks each with no failures, and all
235 products have embedding, embedding_colloc, zeroshot and zeroshot_colloc.

Archive state at snapshot `2026-09-04T20:39:29Z`:

| mode | source | cwave | embed | zero-shot |
|------|--------|-------|-------|-----------|
| S1 | 9,267 | 9,260 | 9,253 | 9,253 |
| S2 | 13,352 | — | 13,341 | — |
| S3 | 13,764 | 13,764 | 13,722 | 13,722 |

Backlog is zero and every residual is now a genuine failure: 49
`invalid_footprint_geometry`, 4 `unreadable_measurement_file`, 3
`missing_input_file` (56 S1/S3, plus 11 S2).

**Remaining for T1 closure:** decide whether the 49 `invalid_footprint_geometry`
cases justify widening the xsar `make_valid` guard beyond the dateline; the
other 7 are unreadable or absent source files and are permanent exclusions.

### T3 — Refresh and restart the Biomass exploration app

- **Accepted:** 2026-08-31
- **Priority:** parallel engineering task
- **Origin:** live application audit

**Goal:** restore a reproducible Streamlit explorer against the current S2
embedding outputs, then make its data contract mode-aware for S1/S3.

**Accepted scope:** follow the migration checklist in
[`APP_REFRESH.md`](APP_REFRESH.md); update the
preprocessor for `embeddings[pol,tile,embed]`, `center_latitude`,
`center_longitude`, `tile_footprint`, and the absence of classifier labels;
choose polarization explicitly; source image chips from current CWAVE tiles or
lazy reads of authoritative L1B products; generate a versioned Parquet
catalogue, embeddings array, optional bounded thumbnail cache, and provenance
manifest; add Pixi preprocess/serve tasks and a smoke test.

**Non-goals:** regenerating every thumbnail before the catalogue can be used;
making old classifier labels appear to exist; converting the archive into a new
data lake; coupling numeric reads to display-resampled imagery.

**Compatibility considerations:** the current shell has a stale
`PIXI_PROJECT_MANIFEST` pointing to the removed `2507_galeio` checkout. Launch
instructions must unset or replace it. Derived artifacts must use writable
scratch storage and carry source/config fingerprints.

**Validation:** preprocess a small deterministic subset; verify row-to-embedding
alignment and product paths; launch Streamlit headlessly; exercise map,
embedding selection, detail imagery, and catalogue export; measure catalogue
load and selected-scene latency before deciding on further materialization.

**Completion criteria:** a fresh shell can run documented commands to build or
reuse validated artifacts and start the app, with S2 scope visible and mode
metadata ready for S1/S3.

**Direction update 2026-09-01:** the refreshed tile explorer is an intermediate
artifact. The accepted product direction is acquisition-level discovery and
tagging through clustering, semantic search/annotation, and few-shot
classification. The staged design and decision gates are specified in
[`ACQUISITION_EXPLORER.md`](ACQUISITION_EXPLORER.md). Existing tile embeddings
remain useful as inputs to acquisition representations, but tiles are no longer
the user-facing catalogue unit.

**Progress 2026-09-21:** resumed the in-project acquisition annotation app.
It now selects either paired OceanSAR encoder and polarization, searches exact
cosine neighbours within selected modes, displays available official previews,
and exports matches with version provenance. All 34,890 catalogue acquisitions
are covered by both 36,525-acquisition feature bundles; feature joins use IDs,
not catalogue row positions. An empty filtered annotation queue crash is fixed.
Seven tests pass, including Streamlit interaction tests for version-dependent
rankings and unchanged annotation records. Fresh-shell commands are documented
in `biomass_proc/README.md`. The broader acquisition discovery, labelled
representation decision gate, few-shot workflow, preview fallback and catalogue
refresh remain open; this does not close T3.

### T5 — Acquisition-scale wind and wave field maps at improved posting

- **Accepted:** 2026-09-04
- **Priority:** prototype with the latest OceanSAR compatibility work in T4
- **Origin:** acquisition-level exploration requirement

**Goal:** generate and interactively plot geolocated wind and wave retrieval
fields over selected full BIOMASS acquisitions, and determine whether an
overlapping sliding-tile inference routine can provide scientifically useful
posting finer than the current approximately 20 km spacing.

**Accepted scope:** audit the latest model and processing scripts for an
existing dense/sliding posting routine; establish the model receptive field,
native tile size, current stride, output variables, and geolocation convention;
prototype overlapping inference at several justified strides on representative
ocean acquisitions; combine overlapping estimates with a documented rule and
quality/coverage counts; write versioned geolocated wind-speed, wind-direction,
and significant-wave-height fields; and add acquisition-preview overlays or
linked field panels to the explorer.

**Non-goals:** presenting display interpolation as new independent information;
claiming an effective physical resolution equal to the smaller posting interval;
inferring over land or invalid samples without an explicit mask; replacing the
current approximately 20 km products before paired validation.

**Compatibility considerations:** distinguish tile footprint/receptive-field
size, inference stride, output posting, and effective resolution in every
manifest and plot. Preserve mode, polarization, sigma0/preprocessing source,
model checksum, overlap aggregation, projection, units, and direction
convention. Keep numeric scientific fields separate from resampled display
layers, and retain links to the full-acquisition preview.

**Validation:** compare current and candidate postings on identical S1/S2/S3
acquisitions; verify spatial coordinates, swath edges, overlap counts, masks,
units, and wind-direction wrapping; measure seams and sensitivity to stride and
aggregation; compare against collocated ECMWF/WW3 fields without treating their
interpolated grids as fine-scale truth; and record runtime, memory, and output
volume. Include visual cases with gradients, fronts, low wind, sea ice, land
boundaries, and known artifacts.

**Completion criteria:** the app can select an acquisition and display its full
preview together with geolocated wind and wave fields; the chosen posting and
aggregation are reproducible; and the report clearly states native support,
posting interval, effective resolution, accuracy, artifacts, and compute cost
relative to the approximately 20 km baseline.

**Progress 2026-09-04:** the existing tiler confirms overlap is expressed in
pixels and stride is `tile_size - overlap`. Smoke array `3654873` compares the
368-pixel model support at 50 m (an 18.4 km tile) with 0, 184, and 276 pixels
of overlap, corresponding to 18.4, 9.2, and 4.6 km posting. These remain posting
experiments, not claims of 9.2 or 4.6 km effective physical resolution. On the
same S2 acquisition, no overlap produced 30 valid tiles in 1:59 and 184-pixel
overlap produced 95 valid tiles in 5:18. The 276-pixel case remains active.

**Progress 2026-09-05 (first wind product):** dense 384-d embeddings for
`BIO_S2_..._DMKBQC` at 0/184/276 px overlap (verified spacings 18.34 / 9.17 /
4.59 km), a persisted embed-only wind MLP applied to them, and versioned
geolocated NetCDF fields plus figures via
`analysis/build_dense_wind_field.py`. The production 384-d producer is used
rather than the latest 192-d encoder, so the features match what the estimator
was trained on. Every output records tile footprint alongside posting.

Embed-only VV+HH nearly matches all-features on wind speed (RMSE 1.657 vs
1.635 m/s at n=9000), which is what makes dense posting viable at all — only
embeddings exist off the CWAVE L1C grid.

**Blocking finding for T5:** the wind MLP's skill is between-scene, not
within-scene. Over the 2,729-product S2 test set, overall correlation 0.867
decomposes into 0.897 between scenes but only **0.226 within** them, with 29%
of scenes negative. Finer posting therefore adds estimates, not information,
and dense fields must not be presented as resolving fine-scale structure. The
ECMWF panel on the sample acquisition shows this directly (bias -0.04 m/s but
anti-correlated). Improving within-scene skill is now the prerequisite for T5's
accepted goal, ahead of any further posting work. See [DONE.md](DONE.md).

**Progress 2026-09-05:** the 276-pixel case completed in 20:04 with 370 valid
tiles, so the full stride ladder on the same S2 acquisition is 30 tiles / 1:59,
95 tiles / 5:18, and 370 tiles / 20:04 at 18.4, 9.2 and 4.6 km posting. Cost
grows roughly with tile count, about 10x for 4x finer posting. All five smoke
outputs are finite and 192-dimensional with four polarizations. Choosing a
posting still requires the paired validation in the accepted scope; these are
posting and cost measurements only.

**Progress 2026-10-01 (error diagrams):**
`analysis/plot_wind_error_geometry.py` generates wind-speed bias and RMSE curves
against ECMWF speed and the acute wind-axis/antenna-look angle, plus joint
speed/angle heatmaps. The figure and CSV metrics are under
[`analysis/figs/t5_wind_error_geometry/`](../biomass_proc/analysis/figs/t5_wind_error_geometry/).
The existing held-out S2 diagnostic supplies 50,117 tiles / 2,732 acquisitions,
192-d embed-only VV+HH, n=9000, seed 0. Metrics are tile-weighted; bins use
2 m/s and 15 degrees, with cells below 50 tiles or 5 acquisitions masked.
Bias is prediction minus ECMWF; antenna look is ground heading + 90 degrees,
folded modulo 180 (0 along look, 90 crosswind). Low winds are overestimated
(+1.66 m/s below 2 m/s); higher winds are generally underestimated. Marginal
angle-bin RMSE spans 1.54–1.67 m/s, with bias +0.27 to -0.10 m/s. The plots
describe absolute retrieval error and do not resolve the within-scene blocker.
Input checksum, diagnostic/model provenance, counts and bin settings accompany
the PNG/PDF/SVG exports.

## Promotion template

### T<number> — Title

- **Accepted:** YYYY-MM-DD
- **Origin:** `IDEAS.md` section

**Goal:**

**Accepted scope:**

**Non-goals:**

**Compatibility considerations:**

**Validation:**

**Completion criteria:**

### T7 — Preserve archives and test complementary polarizations

- **Accepted:** 2026-10-13, explicit user request

Preserve all relevant Biomass scratch archives and study outputs under
`/scale/project/lops-siam-biomass/analysis/qfebvre` before 15-day scratch
cleanup. Copy/checksum verification and path/symlink repointing are scheduled
as **1286940**. Complete marker and exact inventory are under
`biomass_proc/analysis/preservation_20261013/`; originals are retained until
verification and consumer migration. The scratch tree is approximately 1.3 TB.

Existing S2 VV+VH within-scene assessment completed: mean correlation is
0.196 at 5k and 0.222 at 9k, versus VV+HH 0.207 and 0.230; direction improves
with cross-pol but speed does not. Matched raw + incidence three-polarization
(VV+HH, VV+VH, VV+HH+VH) experiment is **1288881**, report **1290353**.
Four families, three seeds, all modes, separate 5k/common 15k; common finite
train/test tiles. Saved predictions permit co/cross residual complementarity
checks. New outputs go directly to project storage. No new result yet.

Ice/open-water detection and ice-edge mapping are the chosen discussion
priority. Existing labels and proposed validation sequence are in
[ICE_RETRIEVAL.md](ICE_RETRIEVAL.md); an ice training campaign has not been
accepted or submitted by this discussion alone.

**T7 update:** matched polarization training/report completed successfully;
only preservation/consumer migration remains running in T7. For common 15k
embed + incidence, VV+HH+VH speed RMSE is 1.654/1.570/1.575 m/s, with modest
mixed within-scene changes. [Durable report](/scale/project/lops-siam-biomass/analysis/qfebvre/studies_20261013/analysis/polarization_20261013/REPORT.md).

**T7 preservation priority:** 1303083 protects embeddings, benchmark datasets
and fitted study outputs while full transfer 1286940 continues. Full verified
completion remains tracked by `preservation_20261013/complete.json`.
