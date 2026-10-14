# MaxSS and neural-field migration — 2026-10-14

After the user confirmed neural-field training had finished, the four deferred MaxSS default/hpc environments were upgraded to FlexLock 0.9.2. All installed-package version and active-destination guard probes passed. This completes the original inventory of 53 environments (49 previously migrated).

Main and neural-field manifests and lockfiles now pin the reviewed wheel. Both AGENTS.md files document disk-reader compatibility, provenance guards, and the shared main-hpc/worktree-source launch convention. The neural-field standalone environment was not created: the existing launch continues using main hpc with the worktree src on PYTHONPATH. Two broken worktree-relative local package paths were made explicit.

Artifact and environment-membership audits found no unrelated dependency changes. The current main hpc Conda package set matches the new lock (zero additions/removals); a full environment synchronization was not performed as part of this step. Installed FlexLock packages were upgraded directly with rollback backups.

The actual neural-field config imported from the worktree under installed FlexLock 0.9.2. Signature validation passed; logger and checkpoint paths followed an overridden fresh absolute save_dir, and validation-panel selection remained unchanged. All nine inspected root files of the retained product-benchmark run had unchanged SHA256 values. No training, inference or MaxSS job was launched. Scientific source edits and untracked files were preserved.

Evidence: migration-results.json, artifact-audit.json, membership-audit.json, hpc-sync-plan.json, agents-updates.json, and [neural-field validation](../2026-10-13-workflow-validation/nf-validation.json). Backups: /ontap/user/qfebvre/flexlock-migration-backups-20261014-maxss.
