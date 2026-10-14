# Isolated SAR coverage gate

Accepted queue-status/CSV rule implemented in
[sar_coverage.py](../../examples/slimmer_workflows/sar_coverage.py). No scientific
SAR code, installed environment, extraction, scheduler job or artifact changed.

The helper reads the authoritative queue once, matches each frozen process member
to its exact task ID, extractor target, SAFE and destination, and requires `done`.
Successful members with a file are reported as present; successful members without
one are empty under the agreed stable-products assumption. Incomplete evidence,
non-success status, wrong bindings and an all-empty cohort block assembly.

Validation: `/tmp/flexlock-no-pandas/bin/python -m pytest tests/test_sar_coverage.py
-q --disable-warnings`: 11 passed, 5 existing OmegaConf warnings. Fixtures use real
SQLite queues and the public record reader. Cases cover present+empty success,
pending/running/failed/interrupted despite a CSV, unknown task, wrong SAFE/path,
missing database, all-empty and duplicate membership.

Adoption requires linking the frozen full SAFE campaign membership to queue IDs
after enqueueing, running this gate after workers stop, and consuming the accepted
CSV mapping in assembly. Missing products after deletion/movement cannot be
distinguished from genuine emptiness by this contract. Present does not distinguish
new production from existing-file skip or certify scientific schema/validity.

## Membership binding and source prerequisite follow-up

Added binding from already frozen SAFE/destination pairs to queue IDs; it refuses
absent members, ambiguous invocation matches and duplicate SAFE membership, and
never overwrites the binding manifest. 15 real-SQLite fixture checks now pass
(same command/environment, 5 existing warnings).

Read-only inspection found suppressed exceptions in enhanced
`sar_ml/data/prepare_l1c.py`: iter_safe_ds logs read failures and continues;
safe_feats logs feature failures and continues. Current success can therefore
represent lost or partial processing. The old T3 pilot uses a different strict
adapter and explicitly preserves its receipt contracts; it was inspected but not
modified or treated as proof of the enhanced extractor's semantics. Its local
AGENTS profile link was stale; the actual processing profile was read at
research-knowledge/conventions/v0.1/profiles/processing.md.

User decision requested: strict failure of the SAFE on processing errors
(recommended), versus preserved partial processing with explicit error accounting.
No scientific source/behavior changed while that decision is pending.
