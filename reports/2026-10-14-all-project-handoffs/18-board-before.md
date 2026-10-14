# TODO

Accepted implementation scope only. Promote an item from [IDEAS.md](IDEAS.md)
after its workflow, constraints, contract effects, and validation plan have
been agreed. Record that decision in [DONE.md](DONE.md) with a date.

Scope note: these items concern the benchmark engine and its planning state.
Architecture and rationale live in the reference documents listed in
[../README.md](../README.md) and are not duplicated here.

## Active

### T12 — Codabench external-worker spike (HIGH PRIORITY, blocks T11 phasing)

- **Accepted:** 2026-09-04
- **Priority:** highest active item; gates the two-phase deployment plan and the
  TN3/TN4 SRR statements that depend on it
- **Origin:** SRR readiness review; documentation check of Codabench compute
  worker and queue management

**Goal:** determine whether an IFREMER-controlled compute worker can be attached
to the **public** codabench.org instance, so that Phase 1 of the deployment can
use the public portal for accounts/UI/queue while all scoring runs on
SOBA-controlled infrastructure with private references never leaving IFREMER.

**Why it is urgent:** TN3's two-phase deployment recommendation, the revised
EvalAI comparison, and the claim that the export/redeploy acceptance test is
satisfied by a real Phase 1 → Phase 2 migration all depend on this working. If
it fails, TN3 must revert to a single self-hosted deployment before the note is
circulated.

**Documentation evidence gathered 2026-09-04** (needs live confirmation):

- the worker attaches through a broker URL, and the documented example targets
  the public instance: `BROKER_URL=pyamqp://<login>:<password>@www.codabench.org:5672/`;
- queue creation appears self-service from the organizer UI, with the broker
  URL displayed and copyable;
- the model is pull-based over outbound AMQP 5672 only, with no inbound ports;
- the worker requires **Docker or Podman**; rootless Podman is supported.
  Apptainer/Singularity is **not** a supported worker runtime.

**Progress 2026-09-04 — offline portion complete.**

Closed by documentation review:

- *How a competition binds to a queue* (was scope item 3): `queue` is a
  top-level property in `competition.yaml`, set to the queue UUID from the
  organizer UI. No separate binding step.
- *Execution time limit*: `execution_time_limit` is a per-phase property,
  default 600 s, organizer-settable. The public **default** queue is separately
  reported as capped near 20 minutes (codabench issue #1455), which is why an
  organizer-owned queue is required regardless of Phase 1.
- *Quota*: the 15 GB per-user quota is real and enforced, and issue #1889
  reports it over-counting (17.7 GB charged for 8.8 GB of submissions). SOBA
  predictions are ~10 MB, so even a 2× accounting error is immaterial.

A minimal competition bundle now exists in `codabench-bundle/`, and the scoring
adapter has been exercised end to end against the real engine offline. Three
integration defects were found and fixed before touching the live service:

1. **`soba_bench` emits a nested score tree**
   `{source: {variable: {group: {metric}}}}`; Codabench requires a flat
   `scores.json`. The adapter flattens it and also exposes every
   `source__variable__metric` so multi-source tasks stay visible without
   inventing an aggregate the scorer never computed.
2. **`json.dumps` emits bare `NaN`**, which is not valid JSON and is rejected by
   strict parsers. `soba_bench` legitimately returns NaN when fewer than
   `MIN_POINTS` (10) reference points match. The adapter now coerces non-finite
   values to `null` and serialises with `allow_nan=False`.
3. **The rejection page leaked the full traceback**, including absolute
   `/scale/...` host paths, to the participant-visible detailed result —
   violating the log-filtering control in TN4 §3.4. Only the terminal exception
   message is now surfaced.

Verified offline: a 34-of-40-target submission scores correctly
(rmse 0.184, coverage 0.85, count 34, n_targets 40) with strict-JSON-valid
output; an unknown-`target_id` submission is rejected with exit 0, a null score
row, and a readable one-line reason.

**Blocking environment findings:**

- **Outbound AMQP 5672 is blocked** from the analysis host tested. The worker
  cannot reach the broker without a firewall change or a differently-placed
  host. Port 443 is open. This is a lead-time item — raise it with IT now, as
  it gates the live half of the spike.
- **Rootless Podman is not usable as-is**: `podman 5.8.2` is installed but there
  are no `/etc/subuid` or `/etc/subgid` entries for the account, which rootless
  user namespaces require. Needs a sysadmin entry or a host where it is set.
- Apptainer 1.4.2 and Singularity 3.8.6 are present, but neither can run the
  Codabench worker; this is expected and does not block (see runtime constraint
  below).

**Scope (remaining, live):**

1. Create a queue on codabench.org and confirm no admin/staff approval is
   required for an ordinary organizer account.
2. Attach a throwaway worker on a non-production host and run one submission
   end to end.
3. Determine how a competition/phase is bound to a specific queue — not covered
   by the Queue Management documentation.
4. Establish whether the documented 600-second default-queue limit applies to
   an organizer-owned queue, and what limits do apply.
5. Record codabench.org terms of service, data retention, and account/competition
   deletion behaviour as dated evidence, in the same form as the EOTDL pricing
   evidence in TN3 §5.12.
6. Check the 15 GB quota against the expected bundle plus submission volume.
7. Confirm the rootless Podman worker path, which is documented separately from
   Docker and may lag.

**Runtime constraint to respect:** the Codabench worker cannot run on the
Singularity-only HPC. Under prediction-only scoring it does not need to: it
executes the organizer-owned scoring program, never participant code.
Participant OCI attachments remain a separate maintainer-triggered lifecycle on
HPC under Singularity. Target topology is a small IFREMER VM with rootless
Podman running the worker, reaching `soba_bench` and private references.

**Decision to close within T12:** where private references live for scoring —
mounted from `/scale/project/lops-siam-sentinel1-workbench` or staged to the
worker VM. This is the only point where the public-instance topology touches the
reference boundary and must be an explicit deployment decision.

**Non-goals:** running participant code on the public instance; making
codabench.org the authoritative result record; publishing any private reference
or non-rights-cleared sample during Phase 1.

**Validation:** one submission uploaded through the public codabench.org UI is
routed to the IFREMER worker, scored by `soba_bench`, and returns canonical
metrics and status to the public leaderboard, with no private reference value
leaving IFREMER.

**Completion criteria:** a written go/no-go on Phase 1 with the five evidence
items above recorded and dated; TN3/TN4 updated to match the outcome.

### T11 — Self-hosted Codabench bundle and contract-period deployment

- **Accepted:** 2026-08-31
- **Priority:** WP2 deployed benchmark; participant-facing shell
- **Origin:** promoted operated-service idea I6 after proposal/WP1–WP2 review

**Goal:** deliver a version-controlled Codabench competition bundle, pinned
self-hosted deployment configuration, and end-to-end demonstration with
`soba_bench` as the sole scientific authority. Codabench owns accounts,
prediction upload, queue/status, and participant-facing leaderboard pages; the
SOBA static site remains the durable scientific report/archive and recovery
surface.

**Task mapping:** use one Codabench phase per `(scientific task, dataset
version)`. GRD, SLC, and ancillary-data choices are input-capability
declarations within a task, not separate tasks. Prove grouped/filtered leader
presentation inside a phase; if Codabench cannot express it faithfully, show a
comprehensive table without a global leader and link to SOBA-generated
input-compatible leader views.

**Implementation scope:** competition pages and starter bundle; canonical
prediction upload/scoring adapter; stable Codabench↔SOBA identities and status;
at least two heterogeneous tasks and multiple input capabilities in one task;
detailed-result links to qualitative reports/model cards; separate optional-OCI
status linkage; worker/private-reference isolation; backup/export, read-only
closure, and clean redeployment without dependence on codabench.org.

**Non-goals:** a second scorer; participant OCI as the scored payload; separate
scientific tasks solely for SLC versus GRD; an aggregate cross-contract rank;
or an indefinite post-project service commitment.

**Completion criteria:** a fresh deployment accepts real canonical prediction
bundles, round-trips canonical results, preserves historical task/dataset
phases, displays scientifically valid leaders, survives failure/restart, exports
all required state/artifacts, and is redeployed from the delivery package.

### T10 — Prediction-only scoring with optional OCI rerun eligibility

- **Accepted:** 2026-08-31
- **Priority:** SRR policy and architecture path; freeze before public intake
  and rerun commitments
- **Origin:** promoted idea I10 after review of Benchmark Policy v1

**Goal:** make `point_predictions` in `predictions.parquet` the sole scored participant
artifact. A participant may attach an OCI reproducibility package to the same
stable submission. After admission and a successful offline compatibility
run, that attachment makes the submission eligible for bounded maintainer-run
regeneration attempts on future compatible datasets. Generated predictions
enter exactly the same validation, import, and scoring path as uploaded
predictions.

**Accepted policy:** OCI availability is scientifically ranking-neutral;
historical results remain immutable per task/dataset version; eligibility is a
bounded rerun attempt, not a lifetime execution guarantee; attachment
admission and rerun eligibility are distinct states; failed, incompatible,
revoked, or missing attachments remain auditable but create no scored row.
Submissions declare their input capabilities and training/calibration/
ancillary-data use. The comprehensive results table may compare all valid
rows, but must identify leaders within compatible input contracts rather than
present an undifferentiated cross-contract rank.

**Implementation scope:**

1. one canonical, bounded prediction intake used by direct files and
   OCI-generated files;
2. a versioned optional attachment contract and stable submission/attachment
   identities;
3. separation of OCI execution from scoring, with a task fingerprint and
   explicit compatibility decision;
4. an eligibility registry plus eligible-only rerun campaigns and immutable
   attempt/status history;
5. leaderboard provenance and attachment/rerun status without an OCI ranking
   bonus;
6. retention, revocation, resources, retry, and failure policies; and
7. integration tests proving file/OCI scoring-path identity, compatibility,
   retry, revoke, and missing-artifact behavior.

**Participant intake direction:** Codabench is the primary contract-period
prediction-upload route under T11. Retain a pre-validation helper and a
maintainer-mediated file-transfer fallback. The OCI is an optional attachment
to either route, not a second scoring route.

**Decisions to close within T10:** whether the attachment is a separate record
or embedded in the submission descriptor; the task compatibility rule; image and prediction retention/revocation; CPU/GPU,
memory, disk, wall-time, scheduling, and retry budgets; exact status
vocabulary; intake ownership/location; and TN1/TN2 prohibited-data wording.

**Non-goals:** a custom public upload service or indefinite post-project
challenge operation; mandatory OCI; a lifetime rerun promise; a ranking advantage for
OCI; changes to the scientific scorer; scoring full-grid diagnostic products;
mandatory DVC; or compatibility machinery for unreleased prototype contracts.

**Validation:** replace the unreleased prototype descriptors with one clean
initial participant contract; no migration or compatibility reader is required.
Keep scientific result history fixed once the public benchmark launches and
reject incompatible tasks before launch. Prove byte-equivalent canonical predictions receive the
same result regardless of intake route, exercise the complete attachment
lifecycle, and rehearse one real low-friction external submission.

**Completion criteria:** direct and OCI-generated predictions share one
canonical path; contracts and compatibility are machine-readable; campaigns
select only eligible attachments; history and public status are correct; the
bounded policy is approved; and a fresh participant can use the maintainer
route without operating benchmark infrastructure.

### T6 — Publish the submission kit

- **Accepted:** 2026-08-18
- **Priority:** next public-facing decision
- **Origin:** maintainer decision after the wind three-format demonstration

**Goal:** release the completed Apache-2.0 `soba-submission-kit` so a fresh
participant can exercise the unified prediction-file contract and optional OCI
attachment, including diagnostic rows for curated use cases/champion cases,
without access to hidden references, registry credentials, or benchmark
operations.

**Completed scope:** the standalone kit, versioned descriptor schema, public
fixture, direct-file and OCI examples, preflight validator, CI, Singularity
pull/run wrappers, containment probes, and application-level OCI acceptance are
implemented. The final tested revision is `316c5c0`; pipeline 241295 published
OCI `sha256:364f21a12dc7...eb9978daa`, which completed the six-row acceptance
run under Singularity 3.8.6 with network disabled. Full evidence is in
[DONE.md](DONE.md#singularity-first-public-helper-decision-2026-08-18).

**Remaining scope:** decide the public repository name and visibility, select
the release tag, publish the reviewed revision, and document maintenance
ownership and contract-release steps. The T13 adaptation is verified (2026-10-01): the
kit, examples and local validator use one `predictions.parquet` keyed by
`primary_key`, with scored and diagnostic rows defined by the public manifest.
See [DONE.md](DONE.md#t13--unified-scored-and-diagnostic-target-contract-implemented-2026-10-01).
Diagnostic rows support maps and never contribute to scores. Do not rebuild or infer image identity
from source equivalence; admission remains digest-based.

**Progress 2026-08-26:** `soba-submit` now provides `init`,
`make-descriptor`, and `validate` commands. It refuses non-empty starter
directories, computes prediction SHA-256 automatically, validates local
descriptor/artifact consistency, and rejects mutable OCI tags. A standalone
`grid_product_v1` validator and four-node champion-case example are wired into
CI. Validation is **10 tests passed** plus an end-to-end CLI smoke run with six
targets at 100% coverage and a valid four-node diagnostic product. Remaining
work at that date was publication/release ownership; the later T13 decision
required unified-contract changes, now verified before participant release.

**Non-goals:** publishing private targets or trusted scoring orchestration
(public metric definitions/examples are tracked by T9); implementing an upload
service or queue; requiring Docker or Podman on the HPC host; claiming VM-grade
isolation from Singularity 3.8.6.

**Validation:** verify the public URL and release tag from a clean checkout;
follow the unified prediction-file and optional OCI README routes, validate
scored and diagnostic rows against the T13 public manifest, and confirm CI tests the fixture/schema and
emits a digest-pinned descriptor.

**Completion criteria:** a fresh user can follow the public README for both
prediction-generation routes and the unified diagnostic-row workflow, and the
repository's ownership and contract-release process are named.

### T9 — Public data and metric toolbox

- **Accepted:** 2026-08-26
- **Priority:** participant-facing task alongside T6
- **Origin:** maintainer direction; promoted participant-onboarding idea I9

**Goal:** provide a small public toolbox that lets participants retrieve named
Sentinel-1 inputs, obtain legally redistributable development reference
samples, and reproduce representative metric calculations locally.

**Accepted scope:** implement manifest-driven Sentinel-1 SAFE discovery and
download through explicitly named provider adapters, beginning with the
Copernicus Data Space Ecosystem for native RAW/GRD/SLC SAFE products. Add a
separate CMEMS route for relevant derived marine/reference products rather than
conflating CMEMS with the native SAFE archive. Verify identifiers, checksums or
provider versions, resume behaviour, authentication instructions, and local
cache layout.

Publish only small reference samples whose redistribution and ESA handoff are
explicitly permitted, plus synthetic fixtures where no suitable redistributable
sample exists. Each sample must carry source, access date, license/terms URL,
allowed uses, redistribution/handoff status, attribution, and expiry or review
date. Provide versioned metric definitions, small input/expected-output vectors,
and participant-side metric helpers; these may reproduce public metric formulas
but must not include hidden references or trusted scoring orchestration.

**Licensing constraint:** SOFAR observations may be used inside the project for
algorithm development under the applicable access grant, but must not enter a
public toolbox, an ESA handoff bundle, or another redistribution channel unless
written permission or a source-specific compatible license is recorded. A
small subset is not presumed redistributable. Use an approved alternative or a
synthetic fixture for public examples.

**Non-goals:** mirroring full Sentinel-1 archives; embedding archive
credentials; publishing validation/test references; promising that every
internal reference source can be transferred to ESA; duplicating the canonical
private scorer.

**Validation:** from a clean environment, resolve and retrieve at least one
declared SAFE, verify its identity, fetch or generate each public reference
sample, reproduce the published metric vectors, and run an automated export
audit that fails on missing license metadata or any denylisted source such as
SOFAR.

**Completion criteria:** a participant can prepare a documented development
input/reference sample and calculate representative metrics without internal
paths or credentials, while the release and ESA-handoff bundles pass the
source-by-source licensing audit.

**Progress 2026-08-26:** the initial `soba-data-toolbox` scaffold implements
checksummed manifest downloads with atomic `.part` cleanup and environment-only
bearer tokens; fail-closed public and ESA rights audits; an explicit SOFAR
denylist; one synthetic, rights-described reference sample; and public
`metrics-v1` formulas/vectors for RMSE, bias, SI, correlation, R², and count.
Validation is **5 tests passed**; both export audits and the metric vector pass,
and tests prove SOFAR rejection, cached retrieval, and bad-checksum cleanup.

EOTDL is the preferred pilot catalog/host for rights-cleared samples and
shareable model artifacts, but it is optional and not authoritative. Remaining
scope: implement live Copernicus Data Space discovery/authentication and one
checksummed SAFE retrieval; add the first real CMEMS-derived sample only after
rights approval; run an EOTDL round-trip/version/license/export pilot; choose
the toolbox license/repository; and replace the download template with frozen
provider records. CI now runs the tests, both export audits and the metric
vector. SOBA manifests/checksums and the OCI registry remain authoritative even
if EOTDL is used.

### T4 — Real-data exercise of the grid-product path

- **Accepted:** 2026-07 (DESIGN phase 4)
- **Origin:** `soba_bench/DESIGN_product_artifact.md`

**Status note (updated 2026-10-01):** completed T13 supersedes the separate
participant `grid_product_v1` route for future case studies. Keep this historical accepted
item until its remaining report work is moved or closed; do not implement a
second participant artifact in parallel.

**Goal:** exercise `grid_product_v1` on real acquisitions rather than only the
synthetic tables used by tests.

**Accepted scope:** curate at least one champion datatake in
`tasks/s1_iw_hs_v2/reports.yaml`, re-render the v2 report, confirm the
full-field maps render from a real product, and land the remaining phase-4
documentation listed in `DESIGN_product_artifact.md`.

**Non-goals:** changing scoring; product artifacts are never read by `score()`.

**Validation:** `pixi run render-site s1_iw_hs_v2` produces champion pages with
full-field maps and the full test suite remains green.

**Completion criteria:** at least one champion datatake is curated, rendered,
and recorded in [DONE.md](DONE.md).

## Open but not accepted

Roadmap phases E (V1 launch, WV), F (V2 launch, IW), and G (MPC handoff) are
tracked in `soba_bench/README.md`. They remain directions rather than accepted
scope; candidate content and the decisions still required are in
[IDEAS.md](IDEAS.md).

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
