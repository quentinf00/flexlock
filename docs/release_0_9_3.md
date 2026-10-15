# FlexLock 0.9.3 — local release

2026-10-15. Builds on 0.9.2; package dependency requirements are unchanged.

- Return payloads live in the authoritative record's `result` section. New core
  execution does not create or overwrite results.json. Legacy sidecars remain
  readable. Direct sidecar readers/output declarations need migration; use
  `load_record` or `RunRecord.load_results`. Upgrade readers before new writes.
- Nested configured targets resolving into Git checkouts participate in source
  discovery. Capture and comparison share include/exclude scope; exclusions apply
  before staging. Explicit repos retain precedence. Auto scopes contain target
  source files, not arbitrary imports; declare helpers explicitly.
- Terminal queue export preserves deferred references instead of masking earlier
  failures. Completed composite stages can supply nested submissions while their
  parent pipeline runs. Authoritative stage evidence is required; reservations
  from other active owners still block binding.
- Cache hits retain the exact selected producer. Absolute Python interpreter
  Slurm profiles no longer receive a false missing-activation warning.
- Destination guards consistently reject symlink loops under Python 3.13 and
  Python 3.11. Layout-2 tests check ancestor ownership rather than omitted pointers.

No cache-default, scientific-protocol or scheduler API change. No new public
prepared-job export flag. The full suite passes: 1,053 passed, two skipped, one
expected failure. SAR's six-stage small-fixture CLI chain also passes.

Detailed migration: [records and source scopes](record_and_source_scope_migration.md).
Rollout evidence: [release report](../reports/2026-10-15-release-rollout/report.md).
Installed in 51 of 53 inventoried environments with 19 validated project pins.
MaxSS was upgraded after its running job completed. SOBA and the project template
remain blocked by project dependency issues; see the rollout report.
Historical records/artifacts and the separate dirty source checkout are preserved.
