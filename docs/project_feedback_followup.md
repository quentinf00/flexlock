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

## Historical products: project-owned exceptions, then fresh baselines

Decision, 2026-10-16: legacy scientific-producer adapters do not belong in the
FlexLock package or its supported API. None was added by this follow-up; the
shared require_product example remains strict. FlexLock is pre-1.0: historical
project layouts and incomplete producer records must not dictate the core design.
This does not create a permanent compatibility commitment for old record readers;
reader retention/removal remains an explicit release decision.

During transition, a project may consume a historical product with incomplete
provenance. It can track the selected file as an external input, recording its
current identity, known origin and evidence gaps. It need not manufacture a fully
recorded upstream stage. If additional legacy acceptance logic is needed, keep it
in that project's code, with the narrower claims explicit. Never rewrite old locks
or present today's checks as evidence of historical source/environment capture.
The existing HAFS-JEPA, MaxSS and SST exceptions remain bounded transition evidence,
not patterns the core must accommodate indefinitely.

The preferred destination is a fresh end-to-end pipeline run after the API and
workflow contracts stabilize. Pin the agreed FlexLock version and project
source/environment, freeze input membership, and rerun project producers and
consumers into fresh destinations using current records, output contracts and
upstream bindings. Validate the new chain's coverage and scientific outputs against
appropriate retained references before adopting it as the baseline for future work.
Historical products can stay as references; they do not need to be upgraded in place.

Plan these reruns in the owning projects when stabilization and compute scope are
agreed. This policy does not launch expensive pipelines now, require rerunning on
every package patch, or imply that unknown historical inputs can be reconstructed.
See the [project handoff](project_adoption_handoff.md#fresh-baselines-after-api-stabilization).

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

**Composite source attribution — implemented, unreleased.** Following the user's
scope decision, shared capture remains in repos and each invocation records its
effective source_scope separately. Config syntax is unchanged; broad shared project
scopes are recommended before narrower stage scopes. Readers/reports expose both,
and source/environment comparisons use the invocation's configured scope rather
than the campaign union. See the [contract and config examples](source_attribution.md).
The earlier two-stage reproduction remains historical evidence of the ambiguity.

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
