# Project-feedback follow-up — unreleased

2026-10-16. Implemented in the validation checkout after 0.9.3. These changes are
not in the deployed 0.9.3 wheel and have not been synchronized into project environments.

## Bounded fixes

- CLI numeric-looking identifier overrides warn without changing YAML parsing.
  Preserve inner YAML quotes; see [CLI examples](cli_reference.md#string-identifiers-and-numeric-looking-hashes).
  Both root `-o` and selected-node `-O` retain their existing scope.
- `py2cfg` uses `__main__.__spec__.name` for `python -m package.module`, including
  src/editable installs. Direct script execution keeps the existing file-relative
  fallback. A module name is not a code snapshot: workers still need the package
  installed or on their import path. Keep submission under an `if __name__ ==
  '__main__'` guard, because importing a target must not submit jobs again.
- `--dump` and `--enqueue` now apply `-M` then `-O` before exporting, just as
  submission does. Previously these exports silently omitted selected-node edits.
  This was exposed by the quoting regression; no new CLI option is introduced.
- Array profiles render `slurm-%A_%a.out/err` by default; single jobs retain
  `slurm.out/err`. With `configure_logging=False`, profile-owned directives remain
  the complete logging configuration. No Slurm jobs were submitted for validation.
- Newly written run timestamps, completion markers and error records include the
  local UTC offset. Old timestamps remain unchanged and readable. Offset-free
  historical timestamps still require their original timezone context; do not
  reinterpret them as UTC. Directory-name formats and SQLite timestamps are unchanged.
- The file-list coverage example skips exactly `.flexlock`, while still reporting
  other unexpected directories. The [chunk example](../examples/slimmer_workflows/chunk_coverage.py)
  demonstrates frozen membership, hashed outcome manifests and named non-OK acceptance.
  These are project helpers, not new core workflow machinery.

## Legacy producer adapter recipe

A pre-contract producer without `_outputs_` cannot satisfy the strict
`require_product` example unchanged. Keep the strict helper for new producers;
put an explicitly named legacy adapter in the consuming project:

1. Select the exact retained producer directory and load it through `load_record`.
   Require its completion marker and authoritative queue/stage evidence where it
   belongs to a queue. A marker alone or a readable placeholder is insufficient.
   For a composite, validate that stage's matching snapshot rather than requiring
   unrelated later stages to have succeeded.
2. Resolve the selected product against that producer's original project context.
   Check its recorded argument against the selected path; do not resolve historical
   relative paths against the new consumer's working directory.
3. Supply a consumer-owned, explicit expected-file contract: required files,
   schema/dimensions/member identities and, where available, trusted retained
   checksums or a reference comparison. Hashing today's bytes establishes today's
   identity; it does not prove those bytes existed at historical completion.
4. Record the selected producer, effective inputs, acceptance method and remaining
   source/data/environment gaps in the fresh consumer record/report. Keep the
   original producer lock and products unchanged. Do not backfill `_outputs_` or
   create historical provenance from current observations.
5. Test missing/wrong products and mismatched membership as well as the retained
   successful case. Keep scientific protocol compatibility a project decision.

HAFS-JEPA, MaxSS and SST already have bounded project adapters reviewed under these
limits; they are examples of declared exceptions, not blanket legacy acceptance.

## Snapshot-ref retention

Source snapshots are anchored by Git refs and can outlive temporary run directories.
Removing a ref may eventually make its commit/tree/blobs unreachable and eligible
for Git garbage collection. A path containing `/tmp` does not establish that its
source evidence is disposable: DB records, downstream lineage, tags or exported
reports may still refer to it.

Before pruning, inventory directory and DB records, retained exports, named tags and
upstream references across the relevant projects; establish ownership and retention
requirements, then retain a recoverable copy of the referenced objects. The existing
`flexlock gc --refs` is not a global cross-project ownership audit. Do not run it as
an automatic migration cleanup. No pruning or artifact move is part of this follow-up.
A safe retention/pruning tool remains a separate proposal.

## Investigations kept separate

**Composite source attribution.** Queued stage snapshots are materialized with the
campaign master's captured repositories. That union is captured source evidence;
it is not proof that every stage imports every captured repo. A stage fingerprint
is still computed from that stage's tracking configuration. Shared capture/comparison
scopes in 0.9.3 do not turn the union into per-stage dependency attribution. The [two-stage reproduction](../reports/2026-10-16-project-feedback/composite-attribution.json)
confirms a.py/b.py are captured together while each config declares one. Before
changing record fields, reproduce differing stage scopes (including two scopes of
the same repository) and distinguish captured trees from declared dependencies in
readers/reports. Do not drop the union and accidentally omit reconstructible source.

**Repeated product hashing.** The strict helper validates all declared producer
outputs on consumption. Several calls for different fields of the same producer
can therefore repeat validation; separate consumers also recheck bytes. A record
can stay unchanged while product files change, so its digest cannot replace those
checks. Investigate batching acceptance of multiple fields once within a consumer,
then measure actual large-file reads before proposing broader reuse. The [local reproduction](../reports/2026-10-16-project-feedback/hashing-duplication.json)
shows four 32-KiB reads for two requested fields of one two-product producer; a
subsequent changed product is still rejected with an unchanged run.lock. Cross-stage
caches or metadata-only shortcuts would need an explicit integrity-policy decision.
No hashing guarantee is weakened here.

Python `smart_run` defaults, cache/pipeline retirement, public prepared-job export
and automatic import tracing remain separate design/release decisions.
