# Project migration, 2026-10-13

User authorized proceeding for idle projects, excluding the MaxSS neural-field
worktree. Initial Slurm inspection found the neural-field job and an interactive
development allocation. Its launch script activates the main MaxSS hpc
environment and adds the neural-field worktree to PYTHONPATH. Thus the main
workspace, its shared environment and aliases must be excluded too.

## Final state

- 49 distinct non-MaxSS FlexLock prefixes installed/verified at 0.9.2. Four
  MaxSS prefixes excluded. Fresh shallow inventory still finds 53 prefixes;
  no additional prefixes appeared. Source checkouts were not upgraded.
- 18 distinct project manifests and Pixi lockfiles pinned to the reviewed local
  0.9.2 wheel. Pin solves used --no-install. The installed environments were
  checked separately; full Pixi synchronization and scientific replay were not
  performed. Existing unrelated project changes were preserved.
- Compatibility notes in 19 distinct consumer AGENTS.md files (22 path aliases).
  Existing instructions outside the managed note are unchanged. Notes distinguish
  successful pins from the remaining installed-environment-only pilot.
- 202 focused execution, binding, ownership and record checks pass under the
  OmegaConf 2.4 dependency combination selected by some new locks. It emits
  resolver-registration deprecation warnings (592 under pytest's filters), not
  failures. This is not full-suite or scientific acceptance.
- No scheduler submissions, scientific source changes or output replay.

Backups: `/ontap/user/qfebvre/flexlock-migration-backups-20261013` for installed
FlexLock files; `pins-before/` and `agents-before/` for project files. Logs,
proposed manifests, installed-package probes and omegaconf24-tests.xml retain evidence.

## Exclusions and corrections

The example_maxss path is an alias of the active MaxSS workspace/environment.
The first pin selection excluded named maxss-ml paths but missed this alias.
Its manifest and lockfile were temporarily changed without environment
installation. Both were restored byte-for-byte from the pre-migration backups,
including through the active main workspace path. Future selection guards use
physical workspace identities and shared environment mappings, not just names.
No MaxSS package prefix was installed by this batch.

The shared FlexLock source still imported by that active environment originally
had no AGENTS.md. A newly added migration-only note was removed to restore its
original file state; consumer-project notes remain. Its preexisting dirty
pyproject/lockfile and other source changes are preserved.

The project_template manifest has duplicate dev dependency tables and requires
better-exceptions>=0.4,<0.5, while the resolver reports only <=0.3.3 available.
A staged table consolidation allowed diagnosing the solve failure. Its manifest
and lockfile were then restored exactly. Its installed prefix is upgraded, but
durable pinning remains blocked by that unrelated debugging dependency.

## Package preservation audit

Initial lock comparison only handled entries with explicit name fields; most
Conda entries encode identity in artifact filenames. Final audit derives those
names and checks complete artifact identities and per-environment membership
(combined over each environment's platform variants). No scientific package
artifacts or memberships changed in retained pins. The smoke lock removes an
unused setuptools artifact along with the old Conda dependency chain; the
project builds with hatchling and declares no setuptools dependency. Other
differences are FlexLock and its dependency set / Conda-PyPI binding aliases.
Future pin guards now parse Conda identities as well.

Final Slurm inspection also found newly launched model-registry overlay jobs.
Their script uses `/scale/project/lops-siam-model-registry/cache/pixi-workspaces/`
outside the inventoried/mutated prefixes; those were not migrated by this batch.

`validation.json`, `artifact-audit.json`, `membership-audit.json`,
`pin-results.json`, `agents-updates.json` and `installations-after.json` record
the final counts and limits. Package/manifest installation is not an assertion
that every project's historical queue or scientific workflow has been replayed.
