# Central review — 260506_hafs--hafs_tools

## Acceptance decision — 2026-10-14

**Decision: accepted — bounded frozen campaign/receipt contract; current-store
coverage and production extension are not centrally certified.**
Inspected the gate and independently verified four declared receipt hashes and
completion markers. Submitted evidence shows bounded scratch downloads and explicit
rejection of a 19-cycle retained gap. The gate's default uses receipt stored_cycles;
check_current_products=True rereads the current zip. Receipt validity cannot prove
a shared store remains unchanged after receipt creation. A central current-store
recheck was stopped after exceeding the bounded review duration; no product written.
Require a current-product check at consumption/production acceptance, or explicitly
state the weaker receipt-time contract. Preserve the missing-cycle decision for the
project owner; the VALIDATION-ONLY accepted-gap file is not production approval.
Failure/partial-product, extension and real scheduler modes remain unvalidated.
Core findings are centrally tracked; do not change existing CLI parsing or disk
contracts independently. Preserve shared stores and historical missing provenance.

Local project feedback is mirrored in `reports/flexlock-adoption/central-feedback.md`.

## Release/follow-up status — 2026-10-16

The unreleased follow-up fixes module target identity under python -m, adds
numeric-identifier override warnings, gives array workers separate default logs,
adds offsets to new run timestamps and corrects the campaign helper's .flexlock
scan. These changes are not in installed 0.9.3; production/current-store coverage
and scientific acceptance limits above are unchanged.

See [rollout evidence](../../2026-10-15-release-rollout/report.md) and
[unreleased follow-up](../../../docs/project_feedback_followup.md).
