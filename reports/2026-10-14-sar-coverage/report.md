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
