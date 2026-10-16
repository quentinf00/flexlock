# Central review — MaxSS submission

2026-10-14. Initial review of report.md; evidence review remains open. This is not
central acceptance or a claim that the project's remaining callers are migrated.

The submission is usefully bounded: main/worktree import checks, explicit bindings,
fresh stage roots, fixture chain and reassessment, with no unauthorized scheduler
run or training. It explicitly lists deferred active configs and raw SQL readers.
Those deferrals prevent treating the whole project as fully adopted; distinguish
acceptance of the I39 pilot from closure of the broader adoption task.

Core findings triage:

1. Composite source union in stage records: inspect actual records and capture
   semantics before calling this incorrect provenance. A campaign source superset
   differs from per-stage dependency attribution. Keep this open for reproduction.
2. Full output SHA on consumption: a verified record digest alone cannot replace
   product checks. The record can stay unchanged while product bytes mutate.
   Performance work may reduce duplicate checks, or propose an explicitly weaker
   integrity contract, but must preserve current default guarantees.
3. Absolute python_exe warning: audit warning conditions independently; an
   absolute interpreter can intentionally select the environment without shell
   activation. This is a candidate bounded quality-of-life fix.

Next review: inspect local patch/records, check concrete producer acceptance and
orchestrator recovery, and state pilot acceptance separately from deferred callers.
No changes to the project's submitted report or scientific code made here.

## Follow-up review of updated submission

The report now includes a user-authorized four-job CPU smoke chain, jobs
1392537/1392576/1392598/1392600. Local check JSON records all stage completion,
absolute paths, declared outputs and producer bindings. This supersedes the
earlier dry-run-only description; it validates scheduler ordering, not the real
GPU/full-size workflow. The local orchestrator was inspected: exclusive ledger,
immediate flush, concrete stage paths and dependency IDs are present. Recovery
uses a new ledger and manually verified stage subset; it is not automatic recovery.

The absolute-interpreter warning is fixed centrally at a0a934b, not yet installed
in 0.9.2 environments. Output-hash cost is in the project acceptance helper; no
unsafe record-digest substitute accepted. Composite source attribution stays open.
The pilot evidence is positive; broader task closure remains pending deferred
active configs/readers and bounded recovery review.

## Acceptance decision — 2026-10-14

**Decision: accepted — bounded I39 local and four-job CPU smoke recipe.**
Independently verified all seven declared smoke outputs and completion markers.
A mocked orchestrator check (no scheduler calls) confirms that failure at the second
submission preserves the first accepted job ID and that an existing ledger refuses
replay. Manual repair requires a new ledger and verified stage subset; it is not
crash-atomic recovery if submission succeeds before ledger persistence.
Full-size GPU execution and deferred configs/readers remain open. Composite source
superset attribution is a core follow-up, not a blocker for the separately submitted
stage recipe. Add unknown-stage rejection to the orchestrator; preserve manual
inspection after any uncertain submission result.

Local project feedback is mirrored in `reports/flexlock-adoption/central-feedback.md`.

## Release/follow-up status — 2026-10-16

The absolute-interpreter warning fix is installed in 0.9.3. The campaign source
union versus per-stage attribution and large-product rehashing questions remain
separate investigations. No record-only integrity shortcut has been accepted.

See [rollout evidence](../../2026-10-15-release-rollout/report.md) and
[unreleased follow-up](../../../docs/project_feedback_followup.md).
