# Urgent fixes: compatibility proposals for review

2026-10-14 proposals, superseded by the user's 2026-10-15 decision: use
in-record results and shared source scopes. See the implemented, unreleased
[migration contract](record_and_source_scope_migration.md). The proposals below
are retained as decision history, not current implementation guidance.

## Return payload versus callable-owned products

Recommend reserving `run.result.json` for FlexLock's return payload on new writes.
Read it preferentially, falling back to historical `results.json` only for legacy
records. Preserve callable-owned `results.json`; refuse a callable-owned collision
with the newly reserved filename. Audit forced rerun cleanup so it does not delete
scientific `results.json` products as though they were exclusively core metadata.
Cover serial, workers, cached reads, composite resume and query readers.

This changes the disk contract for clients directly reading core `results.json`.
Document and audit those callers before a release, just as for queue layout changes.
Historical overwritten products cannot be reconstructed from null return payloads.
A smaller collision-only sidecar would reduce immediate path changes, but leaves
two active result conventions and complicates rerun ownership. A consistent reserved
name is preferable. New filename/default policy needs user agreement before release.

## Source capture versus comparison scope

Keep existing repo include/exclude semantics as comparison scope. Recommend a
separate explicit capture policy for source snapshot paths/exclusions, recording
that scope in provenance. Stage only selected paths into a fresh shadow index;
do not stage 20 GB and remove it afterwards, since Git objects have already been
created. Preserve default full-repository capture initially for compatibility.

Capture omissions must be visible and must not imply full repository provenance.
Require declared data tracking for scientific inputs excluded from source capture.
Validate ignored/untracked files, dirty checkout reconstruction, and stable identity
on small temporary repositories. Exact config spelling and default changes remain
a user/release decision; no automatic inference of source files from extensions.

## Work that needs no feature decision

Terminal YAML export should serialize stored configs without re-evaluating deferred
references. The SAR trace's original failure was its project acceptance helper;
queue export then masked it. Fix export and send the helper correction to SAR.
Clarify nested-target discovery separately from whole-tree hashing and comparison
scopes. Broader target/import discovery is a later enhancement.
