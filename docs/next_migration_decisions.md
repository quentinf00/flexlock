# Remaining migration decisions

2026-10-14. Review proposals, not installed changes. Shared guidelines and local
AGENTS links are in place in 21 distinct consumer checkouts. All 53 inventoried
environment prefixes use FlexLock 0.9.2. Config organization and scientific
workflow adoption are incremental; an upgraded package does not establish either.

## SAR: explicit per-SAFE outcomes before assembly

The inspected `sar_ml/stages/data.py` extractor returns None for an existing CSV,
for no extracted features, and after producing a CSV. `prepare_dataset` silently
ignores absent CSVs. A wrapper observing only those return values cannot certify
legitimate emptiness. Do not infer it from file absence or a log message.

Proposed project change: retain the scientific extraction calculations and write
a required `item.json` only after a known terminal outcome. Give each SAFE its
own receipt directory. The existing CSV can live below that directory; dataset
assembly then needs an explicit feature-path mapping rather than basename lookup
in a shared folder. Train/val/test assembly each gets a separate receipt directory.

Minimal receipt examples:

```json
{"schema": 1, "safe": "/inputs/one.SAFE", "outcome": "produced", "rows": 12,
 "product": "feats/one_features.csv", "sha256": "<full CSV digest>"}
```

```json
{"schema": 1, "safe": "/inputs/two.SAFE", "outcome": "empty", "rows": 0,
 "reason": "No tiles survived the configured extraction filters"}
```

[Executable validator](../examples/slimmer_workflows/sar_outcomes.py) checks SAFE
identity, explicit emptiness, product containment, CSV bytes and row count. It is
an isolated proposal and does not implement extraction or certify scientific CSV
schema. Input/config/source identities remain in the FlexLock invocation record
and frozen campaign manifest; the receipt does not replace those contracts.

Use the existing output hook; no optional-output API is necessary:

```python
_outputs_=dict(item=dict(path='item.json', sha256=True,
    validator=dict(_target_='examples.slimmer_workflows.sar_outcomes.validate_item',
                   expected_safe='${....safe}')))
```

The relative interpolation above ascends from the validator to the stage config.
In an adopted project, move the helper into that project's importable package.
Before assembly, require completed records and healthy receipts for every
process member of the frozen manifest, check each receipt against that member's
SAFE and invocation inputs, and account for explicit exclusions. Receipt validation
alone is not a cohort coverage check. A missing receipt is unfinished or failed.
An all-empty cohort must stop assembly with a clear outcome, rather than concatenate
an empty list. Decide scientific acceptance of empty members before launching.

Historical CSVs may be selected as retained products after explicit project checks;
do not fabricate historical extraction receipts or reinterpret missing files as empty.
Existing-file skip must use accepted retained evidence or refuse the destination.
This changes project bookkeeping and assembly paths, so integration awaits review.
It does not alter the legacy split protocol or resolve its datatake leakage.

## Slurm: keep ordinary submission; defer public export

The private backend materialization seam is implemented and locally tested. Keep
profiles, --after and --print-job-id as the supported workflow. A hold is already
expressible through a profile directive. My recommendation is to defer a new public
export flag until a real workflow requires delayed manual submission: raw sbatch
would leave acceptance, repeated launch and reservation ownership to the project.

If accepted later, a public export proposal must specify destination reservations,
when they may be released, how manually accepted IDs are recorded, and whether
arrays/dependencies may change after preparation. Merely printing a runnable
command does not settle those questions. The private seam adds no installed API.

## Optional caching and project cleanup

CLI caching is opt-in today; Python submit/run_stage still default to smart_run=True.
Do not report caching as removed. New recipes explicitly use False. Next validate
the SST retained-preparation mapping in isolation, updating root anchors before
selecting downstream configs. Keep explicit True compatibility callers and bounded
same-path skip reuse. A future Python default change needs a release decision.

Adopt one useful workflow per project before reorganizing directories. Keep old
configs until their callers are audited, and keep historical artifacts at their
selected paths. No bulk archive or artifact move is needed for the core migration.

## Execution order

1. Review SAR receipt/assembly contract and the decision to defer public export.
2. Build an isolated SST retained-preparation selection example and validate root
   propagation and retained product checks without running expensive preparation.
   The synthetic SST-style regression now passes: a detached config edit leaves
   later selections unchanged, while updating the root before selection consumes
   the accepted retained product without creating the unused preparation path.
   Actual SST preparation configuration adoption remains to be validated.
3. Integrate the accepted SAR contract in a bounded project pilot; exercise a
   produced item, a genuinely empty item, failure and incomplete cohort rejection.
4. Choose the Python caching default for a subsequent release after those callers
   have explicit alternatives. Then update docs, compatibility notices and tests.
5. Adopt reviewed configs gradually; archive only after caller and retention audits.
