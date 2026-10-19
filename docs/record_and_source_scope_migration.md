# Run results and source scope — 0.9.3 migration

2026-10-15. Released as a local 0.9.3 wheel. Installed in 51 inventoried idle
environments; SOBA and the project template remain blocked. See the rollout report (internal validation evidence) for evidence and blockers.

## Return payloads

New executions store the return payload in the run record's `result` section.
Serial/directory records use run.lock; DB records use their authoritative stage
snapshot. The result is written before run.complete. Invocation config/fingerprint
does not include the result. A downstream concrete producer digest covers the
finalized record, including its result; promised producers bind at stage start.

Read with `load_record(directory)['result']` or `RunRecord(directory).load_results()`.
The existing payload convention is retained: dictionaries are stored directly,
other values are wrapped as `{'result': value}`. JSON serialization conventions
(including string conversion for non-JSON objects) remain compatible. Return small
summaries/paths; store arrays, checkpoints and other large products separately.

New records declare `result_storage: record`, including before execution. The
reader never interprets scientific results.json as a return value for such a record.
Historical records without that declaration retain results.json fallback. DB task
status/result columns retain their existing contract. Composite stage results are
available to later stages before the entire composite task finishes.

Core execution and force-reset code no longer writes/deletes results.json as return
metadata. Explicit whole-directory overwrite policies still have their documented
destructive scope. Scientific callables remain responsible for their own products.
Declared `_outputs_` expecting a core-generated results.json must change: it is no
longer generated. A callable-owned results.json can still be declared and checked.

Consumers using direct filesystem result paths must migrate. Old readers expecting
the sidecar cannot read new results; upgrade readers before emitting this layout.
Historical records are not rewritten and lost overwritten products are not recovered.
No new return sidecar is introduced. Existing full-record binding guards remain.

## One source scope for capture and comparison

Configured `_target_` nodes are walked recursively, skipping tracking metadata.
Modules resolving into Git checkouts are grouped by canonical repository path.
Auto-discovered scopes include the target module source files. This supports src
and editable imports but does not trace imports, dynamic code or subprocesses.
Declare extra repositories/helper modules explicitly.

An explicit canonical repository declaration owns its include/exclude scope; with
no include it requests the full non-ignored checkout. Otherwise capture and
fingerprinting stage only the selected include paths minus exclude paths. Both
operations start from an empty shadow index and share the same Git pathspec logic.
Exclusions apply before blob creation. The user's real index is not modified.
Scopes are retained beside the recorded tree; they describe partial evidence,
not complete transitive dependency capture. A campaign master captures the union
of its stages' scopes. An explicit discovery disable still takes precedence.

Captured scope can be broader than a later explicitly requested comparison scope;
comparison cannot reconstruct source omitted from capture. Historical broad trees
remain readable; scoped fingerprints may differ, causing conservative cache misses.
Automatic cache search/default policy is unchanged by this migration.

This supersedes the separate-capture-policy and run.result.json proposals in
urgent_fix_decisions.md, following the user's 2026-10-15 approval of shared scopes
and in-record return values. The local release and partial installation rollout are documented in the report above.

## Unreleased attribution follow-up — 2026-10-16

The next change separates inherited captured repos from each invocation's effective
source_scope, without changing _snapshot_.repos configuration or creating separate
stage snapshots. Broad project-level scopes are the recommended starting point.
Source/environment comparison and reader/report semantics are documented in the
[source-attribution contract](source_attribution.md). This is not in the deployed
0.9.3 wheel; historical source evidence is not backfilled.
