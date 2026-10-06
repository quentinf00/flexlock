# T5 — Explicit registry and uniform logical item acceptance

Date: 2026-10-06. Disposition: isolated engineering acceptance passed; T5/G0
complete at this scope. Production adoption and API consolidation remain T6/T7.

## Source and resulting behavior

Implementation commit `cbdcc65276765d069ee289c4d75dac6083ad62bd` on
`workflow/execution-acceptance`, based on integrity integration `7250c21`.
Original scientific repositories and installed environments were not modified.
The selected checkout is exported through PYTHONPATH to spawned children; the
reused SST CPU environment otherwise imports its older editable FlexLock.

- `flexlock init` establishes an explicit project index/identity without moving
  historical nested indexes; `doctor` explains effective index/preset discovery.
- `flexlock items` and read-only record APIs expose item status, result, execution
  metadata, product/receipt paths and optional artifact health without migrating
  a database or changing recorded status. Health and recorded completion differ.
- Serial and parallel sweeps use the existing queue. Each logical item retains
  its result and source/env/note, including database receipt mode and later appends.
- Shared product roots have separate `.flexlock-items/<task_id>/<stage_digest>`
  receipts and checksum baselines. Callables still receive the product root.
  Overlapping declared products are rejected before execution. Historical failed
  pipeline rows do not prevent the existing skip/resume workflow.
- Distinct-root serial collision guards and skip of healthy stages remain
  supported. Symlinked Python prefixes now work in serial debug frame filtering.

See [contract and commands](../../docs/project_registry_items.md),
[CLI reference](../../docs/cli_reference.md), and the checked-in
[acceptance recipe](../../tests/registry_items_acceptance.py).

## Validation

The full regression suite passed: **751 passed, 1 expected failure**, 39 existing
collection/deprecation warnings; [JUnit](full-suite.xml). The final suite ran
against the clean implementation commit; earlier failing diagnostic runs were
fixed before this acceptance and are not used as final passing evidence.

Fresh [campaign acceptance](campaign-acceptance.json) passed on that commit:
serial shared-root items 1/2, append item 3 with CACHED/CACHED/SUCCESS, earlier
completion bytes/notes retained; parallel shared-root dir receipts; independent
failure/success; read-only item health. Focused tests also cover dir/db modes,
single-item queues, composite stages, overlapping products, corrupt output,
missing database, nested registry avoidance and absent-note preservation.

Fresh [live Slurm acceptance](slurm-acceptance.json): producer **463136 FAILED
1:0**, consumer **463137 PENDING DependencyNeverSatisfied**, never executed;
consumer cancelled after inspection. [Final accounting](final-accounting.txt)
confirms both terminal. Exactly two one-CPU, 1-GiB, one-minute jobs were submitted.
PBS/bootstrap behavior is covered locally; no live PBS or GPU claim is made.

Existing SST reassessment outputs were revalidated read-only against this source:
paired_matchups.csv, provenance.json, assessment.json hashes and assessment
validator passed. Scientific computation was not rerun. Prior SST results remain
in the [T4 report](/ontap/user/qfebvre/sst-workflow-pilot/reports/2026-10-06-frozen-reassessment/report.md).

## Scope and next handoff

This is an isolated implementation and acceptance, not an upstream merge or a
production environment upgrade. Historical delta readers remain compatible but
cannot reconstruct missing past source identity. Undeclared outputs retain their
unchecked behavior; disjoint arbitrary writes cannot be inferred. Skip remains
legacy resume, without identity-safe reservation, retry history or new facade.

Next: T6 scoped documentation cohort, then T7 compiler/kernel/API and representative
consumer migration. Record actual imports and scientific acceptance separately.
Numeric evidence belongs here; shared knowledge cards link this report.
