# Migration toward a smaller FlexLock core

Date: 2026-10-06. Status: accepted direction and staged implementation plan.
M0's root-anchor CLI fix is implemented and validated. Review drafts and executable
examples are available. M1's three reviewed record corrections and an explicit
future-input snapshot correction are implemented in the isolated branch, validated
by 202 compatibility cases and a 33-case focused executor follow-up. The isolated review
follow-up preserves colliding producer identities, binds campaign coverage to frozen input
bytes, and adds controller/queue destination guards. M1 directory identity now rereads selected file paths and contents instead of
reusing weak aggregate metadata. The remaining phases stay open. No production deployment or live-job authorization is implied.

Review companions: [workflow guidelines](workflow_guidelines.md) with executable
configuration/campaign/chain examples, and [Slurm submission proposal](slurm_submission_workflow.md).
Backend materialization is proposed after M1 guards/M2 bindings; a managed prepared-launch
lifecycle is deferred. --after remains.

[Milestone evidence](../reports/2026-10-06-workflow-guidelines-record-contracts/report.md)
records implementation scope and passing checks. The [independent-review follow-up](../reports/2026-10-06-independent-review-followup/report.md)
records lineage/coverage/guard changes and 249 compatibility plus 35 overlapping
focused checks. The [2026-10-07 discovery decision](provenance_discovery_decision.md) retains automatic
provenance and implements known run_lock reads plus labelled heuristics.
M2 concrete existing producers now bind before queued dispatch and are checked at
stage start. 366 distinct selected compatibility/follow-up cases pass, with one existing
expected failure; this is not the full suite. Directory identity has 70 selected checks
passing. [Binding evidence](../reports/2026-10-07-submit-bindings/report.md).

## Target and compatibility boundary

Flex: Python configuration, py2cfg, preset/node loading, @ replacement, overrides.
Lock: readable evidence of effective configuration, source, declared data and
concrete upstream bindings. Practical additions: local debug, scheduler dispatch,
sweeps and bounded task-claim workers. One configured callable invocation is the
basic execution unit. A queue has explicit independent-item membership.

Keep -d/-s/-o/-O, direct run_lock interpolation and sweep sources. Do not require
plan/handle objects, artifact classes or track/arm/attempt schemas to run a function.
Track/arm/run organization is a project convention. Keep a thin ordered -s a b
convenience if it preserves separate records and stops after failure.

Provenance and diff remain useful independently of automatic caching. Workflow
code chooses retained products, handles model continuation and validates cohort
coverage. Mechanical record collisions, wrong paths and misleading success are
library defects; guidelines cannot excuse them.

[Five-recipe map](/ontap/user/qfebvre/workflow-proposal-2026-10-02/plans/details/flexlock-core-recipes-2026-10-06.md)
and [usage-test review](/ontap/user/qfebvre/workflow-proposal-2026-10-02/plans/details/flexlock-cli-usage-review-2026-10-06.md)
are the source rationale. The older plan/launch/resume facade is deferred.

## Phases, deliverables and exit checks

| Phase | Bounded deliverable | Exit evidence | Dependency |
|---|---|---|---|
| M0 — Preserve the CLI idiom | Root-only anchor items merged before selection; ordinary stage sweeps retained; preview/enqueue/dispatch agree | Python config override and root sweeps, local workers, mocked Slurm, mixed fields, scope, dump/check and existing CLI regressions | This change |
| M1 — Correct record/guard contracts | Fix or reject repeated-root composite stage aliasing; correct cross-tag result lookup; reject cache hits with missing authoritative records; specify/hash weak directory identity; pre-submit destination guard | Reproduce each reviewed defect, meaningful regressions; backend.submit never called on occupied destination; clear --force/live-work behavior | M0, independent review evidence |
| M2 — Bind explicit upstreams | Preserve run_lock syntax; record concrete selected producer and value/identity; resolve existing selection once, permit explicit future-path reads; keep discovery distinct | A chosen before dispatch stays A when B appears; missing/changed A follows specified policy; future A plus afterok reads A; direct run_lock lineage recorded | M1 for accurate records |
| M3 — Separate optional policies | Inventory actual callers; separate record/diff functions from automatic cache/search; identify stage-resume/fanout adapters; document defaults/warnings | Fresh execution needs no cache engine; existing opt-in callers and old records continue working; semantic change has a migration example | M1/M2, caller inventory |
| M4 — Exercise five short workflows | Existing commands/configs for fresh, file campaign/reducer, queue continuation, reassessment, explicit chain; project-owned bindings/coverage helpers | Bounded lab and SAR/SST examples; failures and negative cases; large-list queue benchmark with measured submission/provenance overhead | M2/M3 |
| M5 — Adopt, then retire | Update lab/tool generator first, isolated consumers next, owner-reviewed production cohorts later; remove APIs only after replacement use is established | Actual import/version checks, migration diffs, replay of relevant recipes; retention/rollback noted | M4 and consumer owner decisions |

No calendar deadline or full-project rewrite. Each phase should be reviewable and
use local/fake-backend checks first. Live scheduler or real scientific runs require
a justified acceptance case; no GPU training is necessary for API plumbing.

### M0 implementation

The single-stage CLI compiles root-anchor sweep items before root references are
frozen. It delegates resulting ordinary configs to Project.submit and the existing
queue. No new execution engine is introduced. Stage-only sweeps keep their scope;
qualified main.x addresses the root, while bare x remains a stage argument when
both root and stage have x. Mixed dictionaries can update both levels.

The parser's repeated-key/scalar-target spellings remain unchanged. Abbreviated
upstream_run=A,B gets an actionable error in a root-anchor sweep; adding Hydra-like
shorthand can be considered separately, without mixing it into this bug fix.
New root-anchor --dump exports a plain list; --enqueue exports ordinary stage
entries. Interactive editing of multiple root configurations is not supported.

### M1 corrective follow-up

The independent review reproduced three defects in cbdcc65: repeated save_dir
stages overwrite each other's record/result projection; cross-tag dedup returns
SUBMITTED for completed synchronous work; a missing authoritative DB still yields
CACHED with a wrong product path. Keep those reproductions, then fix or reject the
cases. The isolated corrective patch rejects repeated resolved stage roots before
queue/backend construction; collects terminal outcomes by requested task ID across
tags, rejecting active rows owned by another tag inside the queue transaction; and
requires a readable authoritative record for cache hits. No record schema or task
identity format changes. 202 compatibility cases and 33 focused follow-up cases
pass. The follow-up guard uses controller locks and pending/running queue reservations
before force/cleanup/dispatch; held jobs reserve their products. Direct queue mutation
remains under the one-controller rule. Directory checks now reread selected paths and bytes, without aggregate cache reuse. Deprecating
orchestration does not permit compatibility paths to lie.

Smallest same-root composite remedy: reject repeated resolved stage directories
within an item. Stable stage IDs can be an optional later enhancement if consumers
need it. Independent chunks may still share a product directory with disjoint writes
and distinct receipts. Do not convert this into a general artifact ownership system.

Guard destination records before dispatch, including submitted-but-not-started
work. A check followed by an unprotected later write is insufficient for simultaneous
submitters: use a narrow atomic launch claim or explicitly refuse that use. --force
is intentional replacement, not an undocumented way to seize an active writer.
Force replaces the current record and does not archive old evidence; products remain
for in-place rewriting. Preserve evidence or use a fresh path for historical bindings.
Old index fingerprints must not resolve to a replacement record.
One-controller queue guidance remains until a stronger ownership protocol is tested.

Directory identity uses full selected-file content checks and relative paths, for
all directory sizes. Aggregate directory cache reuse is removed: root mtime, file
count and latest child mtime miss nested edits and renames. Overlapping match patterns
are deduplicated; match/ignore selections cannot reuse another selection’s digest.
Records label this method in data_identity; existing data digest fields remain readable.
Empty directories, permissions and timestamps are outside this content identity.
Inputs must stay stable while read; this is not an atomic filesystem snapshot.
The former directory file-limit environment variables no longer weaken checks.
Single-file mtime caching remains a labelled compatibility policy. Do not conflate data
identity quality with cross-stage cache policy. Require readable DB-backed records.

### M2 explicit bindings without a large artifact framework

Keep input='${run_lock:${upstream_run},config.output_path}'. A project helper may
expose related output names from one dataset/model record, without mandatory new
types. Existing runs bind before dispatch; promised outputs have predetermined
producer paths and deferred reads only where necessary. Scheduler job dependency
and producer reference must be intentionally paired by the workflow.

Newest/preset lookup stays a discovery convenience that can be selected once.
Unpinned worker-time newest lookup under --after is not a producer-bound guarantee;
move it to named compatibility/advanced behavior or reject it in the supported recipe.
The executable future-producer example also found controller hashing of nonexistent
promised data. With after, the isolated patch keeps declared data/prevs on the task
and records them on the consumer worker; code repository evidence remains at the
controller. This is a bounded prerequisite, not completion of the M2 binding policy.
Direct run_lock reads now have a lineage/reference record independently of
_snapshot_.data, with canonical producer, requested field, value/default and record
digest captured from one stage-resolution read. Track actual arguments with relative
_snapshot_.data references. Keep automatic target-repository and labelled data-ancestor
discovery; explicit flags disable heuristics, not known references. Canonical explicit
checkout declarations suppress duplicate inferred aliases. Concrete existing
producers now bind before queued dispatch; the worker rejects
any full materialized record digest change before user code. Values and captured
lineage stay paired. Missing required producers defer only under --after or for
earlier stage paths in an ordered pipeline. Pending/running queue placeholders under --after
remain future producers despite their controller record. Other existing records
with missing fields fail before submission; explicit defaults bind immediately.
latest selects at dispatch; unpinned run under --after remains advanced compatibility behavior outside
the supported concrete-producer recipe. This check does not reserve producers or
protect against concurrent mutation after verification. Consumer force does not
bypass it; review replacements and resubmit, preferably to fresh producer paths.
Missing records/required fields fail; explicitly supplied optional defaults
remain deliberate defaults. Content immutability is an additional declared policy.

### M3 keep / optional / deprecate candidates

The [bounded caller inventory](optional_policy_inventory.md) is complete, with
[source/revision evidence](../reports/2026-10-07-optional-policy-inventory/report.md).
SST preparation explicitly relies on cross-run cache selection; SAR pipeline caching
is default-off, while its pilot relies on bounded explicit skip reuse. Existing
Python defaults/adapters remain unchanged. Correct detached-config root propagation
and demonstrate retained-product selection in isolated consumers before changing
behavior. Policy separation and broader adoption remain open.

| Surface | Proposed disposition | Compatibility action |
|---|---|---|
| Python config, py2cfg, @, overrides, explicit run_lock | Core | Preserve CLI and record schemas |
| Local/debug/Slurm, sweeps and worker queue | Core | Accurate status/failure and recorded membership |
| Record/source/data/lineage readers, diff and output checks | Core | Historical reader adapters retained |
| Preset links, init/doctor, run discovery | Lightweight convenience | Make selected scope visible; no compulsory global registry identity |
| Ordered -s a b | Thin convenience | Distinct records, fail-fast; no implicit validated resume claim |
| --check-exists, smart_run, fingerprint cache/search | Optional policy | CLI already opt-in; reconsider Python default smart_run=True with migration warnings |
| Pipeline marker-based skip/resume | Optional compatibility | Explain exact scope; explicit selected-artifact workflows replace broad resume claims |
| submit_chained and ChainedResult fanout | Optional/helper candidate | Inventory callers; provide a short project/Python coordination example |
| Worker-time newest producer lookup with --after | Change supported semantics | Replace with concrete future producer path; legacy behavior explicit |
| unsafe collision bypass | Deprecation candidate | Explicit force contract and default refusal |
| vinc/now naming resolvers | Existing deprecation | Explicit naming policy; retain tests until adapters removed |
| HTML report, MLflow link, skills install, GC/repair | Optional integrations/maintenance | Keep ownership/retention separate from everyday execution |

This table is an inventory direction, not an immediate removal list. Do not rename
public methods just to make the facade look smaller. Avoid a second kernel or parallel
record format. Internals may split by responsibility while wrappers remain stable.
Source comparison scopes must be explicit; selecting target modules does not prove
transitive dependency completeness. Full source evidence and filtered diff can coexist.

### M4 representative workflow checks

- Fresh: configured function, disjoint fresh record, debug/error fidelity, pre-submit
  collision and force; no automatic cache necessary.
- Campaign: frozen file manifest, bounded workers, produced/empty/excluded/failed
  distinctions, explicit earlier-product reuse, project reducer coverage validation.
  Pending recorded queue continuation is different from stage equivalence.
- Resume/continuation: inspect retained records; finish unchanged pending items;
  explicitly requeue selected failures only after old workers stop and failure
  evidence is handled; new invocation for model checkpoint continuation.
- Reassessment: SAR prepared-dataset binding; SST explicit training/checkpoint and
  legacy/native inference pair, matched cohort protocol, no upstream mutation.
- Chain: separate resource profiles and explicit producer path plus afterok; failed
  producer blocks downstream. Future input binding must not search for a newer run.

Use the real pilot manifests/records as examples without retrospectively inventing
historical identity. Existing bounded scientific results are not production adoption.
A thousand-item benchmark is required to assess the original file-listing pain;
small correctness tests alone do not demonstrate scalability. Measure repository
fingerprinting even with smart_run=False: source provenance still costs work. Separate
configuration/queue serialization, source capture, input hashing and scheduler calls
before choosing amortization or removing optional cache policy.

The [bounded thousand-item comparison with Hydra](../reports/2026-10-07-thousand-items-hydra/report.md)
is complete: 56 cases passed and 8,900 local product identities/checksums were
verified. On NFS, reduced-provenance FlexLock medians were 104 seconds locally
and 32 seconds for mocked submission, versus native Hydra's 152 and 75 seconds.
One explicitly tracked FlexLock sample took 452 seconds; repeated module-path
drift checks and source fingerprints require attention. Default legacy cache
miss fallback took 495 seconds, versus 32 seconds for index-only lookup. These
are different provenance contracts, not feature-equivalent speed claims.
Optimize measured repetition while preserving guards; retain optional policy
compatibility until isolated consumers have working replacements. Real scheduler
load, multi-worker contention and scientific adoption remain unmeasured.
The [performance follow-up](performance_core_followup.md) clarifies asynchronous
check boundaries, pointer/outcome consolidation, a proposed manual config-search
command and the verified nextgems month-config replacement. Automatic discovery
removal is not yet implemented; measured performance is not accepted scalability.

The [first preparation optimization](../reports/2026-10-08-preparation-reuse/report.md)
at 0629889 reuses effective executor configs across guard passes. Fresh 1,000-item
cache-off medians fell from 30.807s to 23.315s (three repeats), with equivalent queue
payloads and 183 distinct focused cases passing across rechecks. File count remains
2,007 and peak RSS increased about 7.1 MiB. Next: safe freezing/binding reuse;
source-worker repetition and bookkeeping consolidation remain separate work.

The [second preparation slice](../reports/2026-10-08-freeze-binding-reuse/report.md)
at a32d227 reuses freeze/bind working copies and skips binding only when full
freezing leaves no interpolation. Median is now 20.209s (three repeats); 198 focused
cases pass, queues remain equivalent, and file count remains 2,007. Next inspect
repeated queue reads/materialization; escaped-literal compatibility and tracked
worker source costs remain open. No production scalability acceptance follows.

The [queue-reader slice](../reports/2026-10-08-queue-record-selection/report.md)
at 6211ef6 filters before decoding and uses optional safe C record parsing;
155 focused cases pass. Median 19.948s versus 20.209s establishes no meaningful
additional elapsed speedup. Unprofiled phase evidence redirects attention to
merging/freezing and guard/reservation metadata work. Next inspect repeated
ancestor probes while retaining lock/ownership guarantees and historical readers.

The [bounded preparation I/O pass](../reports/2026-10-08-preparation-io/report.md)
at a27a304 defaults to two joined I/O workers for guarded metadata/reservation
work. Interleaved original/1/2/4 medians: 16.120/17.724/15.249/15.223s; two matches
four without its variation. Default focused checks: 120 passes, two expected
serial-only skips. Locks, active queue ownership and pre-submit failure barriers
remain intact; file count stays 2,007. Config process compilation still requires
resolver/context and startup-cost investigation; no production scaling acceptance.

The [process-compilation prototype](../reports/2026-10-08-config-processes/report.md)
shows isolated-process parallelism is viable for the two canonical fixtures:
plain 1,000-item compilation 4.246s serial → 1.790s with four processes, with
equivalent configs/provenance and startup included. Parent-only custom resolvers
require reconstruction, small sweeps can slow down, and a four-process producer
run took 45.140s. This investigation changes no runtime defaults. Eligibility,
serial fallback, CPU budget and end-to-end semantics must precede integration.

## Rollout and stop rules

The [full process-preparation experiment](../reports/2026-10-08-process-preparation/report.md)
adds an opt-in canonical-config compiler at fd4428c, preserving OmegaConf transport
and serial fallback. Default adoption is rejected: plain serial/2/4 total medians
are 19.413/22.406/16.842s; producer-bearing 28.393/24.363/94.644s, with a 186.817s
total slow run. The delay's root cause remains unresolved. Serial compilation and
two-worker metadata I/O remain defaults. Next reduce repeated executor merges of
already-compiled items while preserving public partial-override semantics; avoid
expanding process/context machinery as a prerequisite for the slimmer core.

The [compiled-item guard reuse](../reports/2026-10-08-compiled-guard-reuse/report.md)
at 1244e70 removes repeated executor merges for frozen Project items while keeping
low-level partial/default/historical merges intact. Matched plain and producer
medians improve 17.031 → 14.128s and 26.560 → 23.447s; serial compilation remains
default. Acceptance: 161 distinct passes, two expected skips, 16 equivalent queues,
100 product checksums and matching source trees/env. Files remain 2,007. Next
inventory pointer/marker bookkeeping and remaining preparation phases; preserve
lock inodes, ownership/history and provenance when considering consolidation.

The [bookkeeping inventory](../reports/2026-10-09-bookkeeping-inventory/report.md)
rejects a pointerless nested prototype despite halving prepared files (2,007 →
1,007): median gain is only 6.1%, and current upstream binding can accept an old
record while an ancestor replacement queue is pending. Keep current writers.
Next consolidate private queue-reference readers and fix ancestor ownership
detection, then measure large upstream cohorts before any versioned descriptor
writer migration. A later pointer/marker merger saves a completed-item file,
not a prepared-item file. Preserve stage completion and immutable item source
evidence; do not merge atomically replaced metadata with a stable mutex inode.

The [queue-reader consolidation](../reports/2026-10-09-queue-reference-readers/report.md)
at 8ad211c now guards required producer bindings against active ancestor queues,
retains exact allowed future paths and centralizes legacy marker reading. Optional
resolver policy and writer formats remain unchanged. 166 focused passes, two
expected skips and 72 overlapping legacy rechecks support isolated acceptance.
Preparation is essentially unchanged (13.373/13.289s); 100 future bindings against
1,000 pending rows still cost 13.299s. Next profile/optimize repeated active-row
decoding and destination lookup with mutable ownership intact. Pointer omission
still needs older-reader compatibility; no production adoption is established.

The [safe ownership parsing pass](../reports/2026-10-09-ownership-yaml/report.md)
at 1512422 reduces the pending cohort median 13.040 → 6.490s with optional
CSafeLoader and SafeLoader fallback. 126 passes/two expected skips, equivalent
configs/bindings; status/task edits and symlink changes remain visible. No schema,
writer or ownership-cache change. Next investigate repeated row scans/destination
resolution; keep file reduction behind older-reader compatibility. Production
installation unchanged.

The [scan-local destination pass](../reports/2026-10-10-destination-resolution/report.md)
at da91f41 shares parent resolution within each ownership check, inspecting final
symlinks separately. No map persists across checks. Matched pending median
2.600 → 1.919s (26.2%); 130 passes/two expected skips, ten equivalent queues.
Preparation primary/follow-up results conflict, so no stable speed conclusion there.
Next address repeated row decoding/scanning without expanding to a persistent
index or caching mutable ownership answers. Files remain 2,007; production unchanged.

T7 implements this plan. T6 can migrate invariants and source routing independently,
without copying speculative execution APIs. The shared knowledge repository links
actual tool semantics; it does not become another CLI manual.

Keep source/consumer selection explicit, including spawned Python imports. Default
changes occur only after caller inventory and working replacement examples. Record
fix availability, isolated validation, installed adoption and scientific revalidation
separately. Stop widening adoption if receipts/results are ambiguous or a guard can
fail after dispatch. Do not expand the scope to general DAG scheduling to resolve a
local defect. Optional workflow shells can follow repeated demonstrated demand.
