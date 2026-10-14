# Project instructions accompanying a FlexLock migration

Update the project's AGENTS.md when its FlexLock installation is migrated.
Preserve existing instructions and document the actual installed version,
affected environments, compatibility changes, validation limits and whether
project manifests/lockfiles have been repinned. Do not mark a deferred project's
installation as upgraded. Do not substitute a full research/reporting workflow
migration for this compatibility note.

The 0.9.2 rollout's per-project text and applied-file list are retained in
`reports/2026-10-12-pandas-removal/`. Subsequent rollout batches should update
that section after successful installed-package verification. Unmapped/orphan
environment prefixes require project identification before project instructions
can be changed.

The [2026-10-13 rollout](../reports/2026-10-13-project-migration/report.md)
records the later idle-project installations and durable pins. Check physical
workspace/environment identities when excluding active jobs: project aliases
can share both source files and environments. Preserve shared source checkouts
still imported by excluded jobs. A successful package probe is distinct from
full environment synchronization and scientific workflow validation.


## Shared recipes and local project notes

Maintain generic recipes in workflow_guidelines.md and link them from each project's
AGENTS.md alongside the applicable release. Keep concrete entrypoints, environment/cwd,
artifact bindings, coverage decisions and exceptions local. Preserve pre-existing
research/knowledge/reporting instructions. The 2026-10-14 rollout added workflow
sections to 21 physically distinct consumer files; aliases were deduplicated.
See reports/2026-10-14-project-workflows/updates.json for paths, hashes and backups.
Project starting-point guidance is distinct from actual adoption: record concrete
run selections after validation, rather than inventing missing bindings.
