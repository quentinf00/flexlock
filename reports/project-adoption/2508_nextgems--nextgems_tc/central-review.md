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
