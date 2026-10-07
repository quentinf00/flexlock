# Decision: automatic provenance discovery in the smaller core

Accepted 2026-10-07. Automatic provenance recording remains core functionality.
Scientific artifact selection, cohort validation and decisions about reuse remain
workflow responsibilities. This decision refines M1/M2; it adds no pipeline planner.

## Track what the callable receives

Prefer `_snapshot_.data=dict(dataset='${...input_path}')` inside a stage config.
An input_path override then changes both the callable argument and tracked data.
The relative reference survives stage selection, detachment and renaming. Avoid
repeating the original run_lock expression or keeping its old producer in prevs
when that producer is no longer independently consulted.

Explicit prevs remain useful for genuinely separate dependencies, such as a
normalization/configuration record consulted independently of the selected input.

## Known references are recorded automatically

A direct `${run_lock:A,field}` read establishes a reference to A; no filesystem
ownership guess is necessary. Stage resolution records A's canonical path, requested
field, returned value, default usage and producer-record SHA256. All fields from A
use one coherent read for that resolution. Lineage copies metadata from that read
rather than substituting a later record. The digest identifies the record that was
read; it does not establish product content identity or producer success.

A missing record with an explicit fallback is recorded as fallback usage and gets
no fabricated producer lineage. Missing required records/fields fail. A readable
failed record remains readable; accepting its products is a separate project policy.
Directory and DB-backed records use the same reader. Existing record layouts remain
readable; transient capture buffers are omitted from persisted callable config.

## Keep bounded heuristics, with visible evidence

`_snapshot_.discover` accepts `repos` and `prevs` boolean flags, both True by default.

- Repository discovery follows `_target_`. An explicit declaration for the same
  canonical checkout suppresses an extra unfiltered automatic alias; explicitly
  named scopes remain authoritative. Additional repositories must be declared.
  Discovery failures warn that source evidence is absent. For deliberate untracked
  targets, disable repos discovery explicitly.
- Data-ancestor discovery examines only declared data paths. A containing record is
  labelled `data_ancestor` in the record's discovery section. Containment does not
  establish output ownership, completion, compatibility or scientific acceptance.
  Disabling prevs discovery disables this heuristic, while retaining explicit prevs
  and known run_lock references.
- A future association through declared outputs must be unambiguous. Shared product
  roots, external products and multiple owners need an explicit selected producer
  when ownership cannot be established. No global file/record scan or newest-run
  substitution is introduced by this implementation.

## Current implementation boundary

The implemented capture is at stage resolution: synchronous local execution binds
before destination creation; queued consumers bind on the worker, including promised
future producer paths paired with --after. This does not yet freeze existing producer
values before scheduler dispatch or reject intervening changes. That remains M2 work.
The capture affects provenance, not automatic cache equivalence or resume policy.
Directory identity now rereads selected relative file paths and bytes; data_identity
records the method. Thousand-item source/queue/discovery overhead still needs measurement.

See [guidelines](workflow_guidelines.md), [migration plan](slimmer_core_migration.md)
and [acceptance evidence](../reports/2026-10-07-provenance-discovery/report.md).
