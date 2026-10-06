# T5 — Execution acceptance milestone

2026-10-06. Isolated checkout `/ontap/user/qfebvre/flexlock-execution-validation`,
branch `workflow/execution-acceptance`, base integration `7250c21`.

## Results

- Live FlexLock Slurm backend acceptance passed: producer **444993** FAILED with
  exit `1:0`; consumer **444994** PENDING / DependencyNeverSatisfied, never ran,
  then cancelled by the acceptance driver. Producer task DB persisted `failed`.
- **56 foundation tests passed** with the existing SST CPU environment and explicit
  `PYTHONPATH` selection. They cover CLI/worker/composite failure, output corruption,
  serial/parallel reuse, index discovery, task-dir/DB and historical record readers.
- **Four adoption recipe tests passed** across n_jobs=1/2 and task_record=dir/db.
  Explicit project `.flexlock/` initialization before outputs exist lets sibling
  result roots discover completed items with glob fallback disabled. Logical item
  payload/config/fingerprint identities agree; receipts remain readable in both modes.
- The bounded SST consumer declares SHA256 plus pairing/coverage contracts; intact
  outputs validate, and copied corrupt/deleted outputs reject reuse. See
  [SST report](/ontap/user/qfebvre/sst-workflow-pilot/reports/2026-10-06-frozen-reassessment/report.md).

## Source-selection trap

An initial 56-test run without explicit PYTHONPATH passed 55 and failed the Slurm
bootstrap case. The parent imports the checkout, while spawned Python resolves the
older installed editable FlexLock ahead of the bootstrap's appended cwd. Explicit
PYTHONPATH fixes the selected source for parent and children. This is environment
adoption evidence, not a patch to the backend. The live test already exports the
checkout path. Package version alone does not identify source correctness.

## Supported recipe and remaining T5 scope

Use one immutable output root per logical item and an explicit project-level
`.flexlock/` directory (or FLEXLOCK_INDEX). Export the selected code roots to child
processes; do not assume a parent import probe selects child imports. Existing index
and task record APIs support this bounded recipe without a new execution facade.

**T5 remains open for general uniform logical receipts/status and shared final-output
roots.** Existing shared-save-dir tests preserve only one directory receipt; they
cannot prove all logical items discoverable from that directory. These checks do
not implement an explicit registry initialization command, ownership/reservation,
retry history or identity-safe resume. No production environment was upgraded and
no core tool code changed. T7 API consolidation is still dependent on those contracts.

## Reproduction and retained evidence

```bash
PYTHONPATH=/ontap/user/qfebvre/flexlock-execution-validation /ontap/user/qfebvre/work/projects/251218_sst/sst_ml_zarrpatch/.pixi/envs/cpu/bin/python -m pytest tests/test_workflow_integrity.py tests/test_index.py tests/test_task_records.py tests/test_run_record.py tests/test_workflow_adoption_recipe.py -q
```

Live acceptance uses `tests/slurm_failure_acceptance.py` with a fresh output root;
it submits two one-CPU/1-GiB/one-minute jobs and cancels its blocked consumer. Recorded
runtime root: `/ontap/user/qfebvre/flexlock-execution-validation/acceptance-runs/slurm-20261006`.

[Live evidence](slurm-acceptance.json), [final accounting](final-accounting.txt),
[foundation tests](foundation-tests.xml), [recipe tests](recipe-tests.xml).
