# In-record results and shared source scope — 2026-10-15

User-approved implementation in the validation checkout. No package installation,
scientific campaign, project artifact rewrite or historical record migration.
Contract and caller migration: ../../docs/record_and_source_scope_migration.md.

## Implemented

- Serial returns finalize run.lock.result; queued returns finalize their stage DB
  snapshot and directory lock when present. Persistence errors prevent completion.
  A result_storage declaration distinguishes new records from legacy sidecars.
  Shared readers prefer recorded returns and read historical results.json only for
  legacy records. Forced pipeline/sweep reset no longer deletes scientific
  results.json. No new sidecar. Dict/scalar payload conventions remain compatible.
- Capture and fingerprinting share clean shadow-index staging with identical Git
  include/exclude pathspecs. Excluded bytes never enter Git; Git status does not
  refresh the real user index. Nested configured targets in editable/src checkouts
  are discovered and grouped by canonical repo. Explicit repo names/paths/scopes
  retain precedence. Auto scopes select target source files; imported helpers and
  subprocess repos need explicit declarations. Campaign capture unions stage scopes.
- API, current reference/usage docs and guidelines updated. Prior proposals are
  labelled superseded. No change to automatic cache-search defaults or installation.

## Evidence

New integration checks cover serial, directory queue, DB queue and composite
results; scientific results.json survives; cache and force read the recorded
payload; downstream result.metric binds at stage start; legacy sidecars still
read; new unfinished records do not mistake scientific JSON for return metadata.
Temporary Git repositories verify nested editable imports, explicit/discovery-off
precedence, stage scope union, capture/comparison tree equality, absence of excluded
Git blobs, and a byte-identical real index.

Broader checks before full run: 127 execution/binding/fingerprint tests passed,
with one old mock updated for added scope arguments. 103 query/index/preset tests
passed; their two fixture assumptions were migrated (DB records own returns;
producer records replace auto-generated result files). Follow-up checks of those
corrections plus return/scope tests: 22 passed. The real-index test was corrected
in the implementation and separately passed all 3 scope tests.

Full suite: 1,052 collected; 1,041 passed, 2 skipped, 1 expected failure, 8 failed
in 362.43 seconds. One introduced explicit-name precedence regression was fixed;
follow-up utils/discovery/source suite: 67 passed, 1 expected failure.
Seven other failures reproduce on an untouched HEAD archive (7 failed, 18 passed,
2 skipped):

- Symlink-loop expectation differs under Python 3.13. The same test passes under
  the SAR Python 3.11 interpreter using pytest's pure-Python runner.
- Three injected reservation failures assume nested queue pointer writes, which
  layout 2 intentionally omits.
- Three preparation-reuse tests likewise require an omitted nested pointer file.

These are baseline issues, not new result/scope failures. Production code and
those unrelated tests were not changed to hide them. Full-suite log retains the
pre-correction explicit-name failure; discovery-followup.log records its fix.
No claim of an entirely green library suite or fresh throughput benchmark.

## Release follow-up

Before installation, audit direct core results.json readers/declarations in projects
and migrate them to shared readers or record.result. Upgrade all readers before
producing the new layout. Explicitly review helper/source scopes for active recipes;
target-file discovery does not establish transitive import coverage. Do not claim
old HAFS-JEPA records acquired its later sibling declaration. Existing materialized
producer digest guards are unchanged; results finalize before completion.
