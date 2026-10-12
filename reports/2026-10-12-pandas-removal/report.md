# Pandas removal and project compatibility notes

User requested removing pandas when unused and updating AGENTS.md during
project migration. Runtime search found no direct pandas imports. Removed the
dependency from pyproject.toml and built a new 0.9.2 wheel, preserving the
previous 0.9.1 artifact and historical records.

Clean offline environment `/tmp/flexlock-no-pandas` contains no pandas. Installed
wheel imports from its own site-packages; its METADATA has no pandas requirement.
59 focused tests pass in that environment (`tests.xml`): queue layout, concrete
producer binding, task records and mocked optional MLflow integration. Tests
exercise checkout code matching the wheel. This is not real MLflow integration
or scientific acceptance. No real MLflow installation is needed to establish
that FlexLock itself no longer depends on pandas.

Refreshed Slurm project work directories before rollout: SST, HAFS-JEPA, biomass,
MaxSS and NextGEMS still have active/pending jobs and remain deferred. The 0.9.2
batch updates the 15 previously upgraded idle prefixes and seven idle prefixes
previously excluded by pandas 3. All 22 installations pass installed-package
version/import-path, dependency metadata and pointerless active ownership probes.
Other dependencies remain unchanged. Backups are stored under
`/ontap/user/qfebvre/flexlock-migration-backups-20261012-092`.

Updated/created AGENTS.md in 10 identified migrated project roots. Existing
instructions preserved; notes cover the stricter execution contracts and
versioned queue layout, pandas removal and rollout limits. `agents-updates.json`
lists targets; `agents-before/` preserves their original text. Project writes
required escalation because the project mount is read-only in the sandbox.

No project manifest/lockfile repinning or scientific replay. Ordinary Pixi sync
can restore the previous package; project notes explicitly state this. Deferred
projects have not been marked migrated. Some historical environment prefixes
have no mapped current project alias, so no project instructions were fabricated
for them. Future batches must identify those owners and update AGENTS.md after
successful installed-package verification.
