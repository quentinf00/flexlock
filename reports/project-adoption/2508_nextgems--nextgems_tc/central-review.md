# Central review — NextGEMS storm preprocessing

2026-10-14. Reviewed submission, retained/smoke coverage JSON and campaign gate
source. Bounded campaign evidence is positive; full/repair processing and broader
plain-script workflow migration remain outside validated scope.

Corrected the central TRANSITION row: nextgems_tc uses storm-catalogue chunks.
Month sweeps belong to nextgems_tc_tracking. Old rollout backups preserve the
mistaken starting-point text as historical evidence; they are not current guidance.

The smoke aggregate has three ok and one explicitly accepted missing_zarr outcome;
unaccepted outcomes block aggregation. The declared chunk manifest binds the frozen
membership and carries per-storm outcomes. This is a useful simpler-core example:
a queue task can succeed while reporting individual failed/missing members, and
the project coverage gate decides whether to accept the collection.

The legacy accounting says zero accounting issues, NOT complete healthy coverage:
9,710 ok + 86 missing_zarr + 35 failed + 3 unreadable = 9,834 process members,
plus explicit exclusions in membership. Products were checked for presence/nonzero
size, not content. No historical source/data evidence was reconstructed.

Follow-up: link this corrected project scope from local AGENTS/task text; document
per-storm product integrity scope clearly when adopting beyond the small bit-identical
smoke. Do not silently accept failed/unreadable outcomes as scientific success.
Snapshot-ref retention/pruning needs its own ownership audit; no automatic cleanup.

No project source, submitted report, retained products or jobs changed by this review.

## Acceptance decision — 2026-10-14

**Decision: accepted — bounded frozen storm-chunk smoke/accounting recipe.**
Independently verified both declared chunk manifest hashes/completion markers.
Re-executed the read-only gate: three ok/one missing_zarr; the missing outcome blocks
acceptance without an explicit accepted outcome and passes when missing_zarr is
explicitly accepted. This checks accounting, not a decision to accept production
gaps. The recheck used an available 0.9.2 SST interpreter with the NextGEMS source
path because this checkout's default interpreter lacked FlexLock; validate the
intended campaign interpreter before further execution.
Correct local month-sweep guidance and state clearly that current per-storm product
checks establish presence/nonzero size rather than full byte identity. Full repair,
production integrity and unrelated plain-script workflows remain outside scope.

Local project feedback is mirrored in `reports/flexlock-adoption/central-feedback.md`.

## Release/follow-up status — 2026-10-16

The unreleased follow-up adds an executable chunk-outcome coverage helper and
retention guidance. It preserves explicit named acceptance of non-OK outcomes and
does not certify per-storm product bytes. Snapshot refs are not automatically pruned.

See [rollout evidence](../../2026-10-15-release-rollout/report.md) and
[unreleased follow-up](../../../docs/project_feedback_followup.md).
