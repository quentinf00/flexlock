# FlexLock 0.9.1: execution validation release

This is a local validation release, not a published PyPI release. It packages
the execution-validation branch, including earlier work accumulated since the
shared source checkout at `660245e` (which reports FlexLock 0.8.2). It is not
only the pointer omission patch. Older environment metadata often reports other
versions; editable installs must be identified by their actual source revision.

## Contents

- Python configuration, `py2cfg`, overrides, preset/node `@` replacement, sweep
  files and `${run_lock:...}` remain available. Root-anchor CLI sweeps are fixed.
- Concrete existing upstream records bind before dispatch. Stage startup rejects
  changed/disappeared producer records. Promised inputs with `--after` retain
  their exact selected path and bind when available; source/data evidence is
  captured when the promised inputs exist.
- Destination ownership and collision checks happen before queue mutation and
  scheduler submission. Active queued work cannot be bypassed by `--force`.
- Retained records, lineage identities, declared output validation and truthful
  failure/completion handling are strengthened. Results expose queue/task/record
  identities and scheduler job IDs. `--after` supports separate scheduler jobs.
- Preparation avoids repeated config merges/binding, unnecessary queue decoding
  and repeated path work. Metadata I/O uses two bounded I/O workers. Optional
  spawned compilation remains off by default. Fingerprint tree capture skips
  unused dirty-status scans while still capturing a fresh source tree.
- Queue layout 2 omits locators for fresh outputs under an authoritative ancestor
  `run.lock.tasks.db`. Existing/external locators and mutex files remain. The DB
  records layout 2 and minimum reader 0.9.1. This declaration cannot make an older
  reader safe; environments reading new queues must actually be upgraded.

## Compatibility

No existing public function was removed in the inspected main API/config,
snapshot, executor, runner and resolver modules relative to `660245e`; changed
signatures append optional arguments. This is not a promise that every older
installation or undocumented helper remains compatible.

Observable behavior changes require project checks: occupied/actively owned
destinations can now be rejected; changed producers can fail a queued stage;
invalid declared outputs and missing authoritative records prevent successful
reuse; failed workers/queues surface failures instead of apparent success.
Clients reading `.flexlock-queue.json` directly must use the shared readers.
These are stricter execution contracts, even where call signatures are unchanged.

Automatic cache discovery/defaults, legacy policies and the existing pipeline
conveniences are still present. Their retirement is a subsequent migration.
Backend materialization without submission remains a proposal. Pandas 3 support
is under investigation; this wheel retains `pandas>=2.3,<3`.

## Workflow and rollout scope

The library ships documentation for config patterns, track/arm/run conventions,
file-list coverage, explicit reuse and small multi-resource orchestration scripts.
These are guidance, not a project schema or orchestration engine. No project
`AGENTS.md`, research-knowledge system or reporting convention has been migrated
by this release. Those workflows require their own adoption/review step.

202 focused execution/reader/binding/lifecycle tests pass. The first rollout
installed the wheel in 15 idle compatible prefixes, with backups and independent
installed-package ownership probes. Active/pending-job environments remain
unchanged at the user's request. Other dependency mismatches remain open.
Project manifests/lockfiles have not yet been repinned; Pixi sync can restore an
older package. This is an installed-environment pilot, not completed project
migration or scientific acceptance.
