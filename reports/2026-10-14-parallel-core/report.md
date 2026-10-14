# Core progress alongside project adoption

Projects own scientific adoption independently. Parallel core audits produced a
bounded automatic-cache correctness fix and a Slurm validation improvement.
No public signatures/defaults, installed packages, scheduler jobs or scientific
project source changed.

Serial and sweep cache-hit paths now load the producer already selected rather
than repeat discovery without the original comparison filters. Agent validation:
43 cache/guard/index/pipeline compatibility checks pass. Exact source/test evidence
is in [cache selection](../2026-10-14-cache-selection/report.md).

Slurm script validation recognizes an explicit absolute python/python3.x invocation
as deliberate interpreter selection. It no longer requires an activation command
for that case. Relative interpreters still warn; commented commands do not suppress
the warning. This heuristic does not certify compute-node dependencies or libraries.
Validation: tests/test_slurm_validation.py and tests/test_slurm_materialization.py,
32 passed, 5 existing OmegaConf warnings, with /tmp/flexlock-no-pandas/bin/python.

Historical release/performance documents now have current rollout context rather
than presenting the initial batches or pointer prototype as the latest state.
MaxSS's first adoption submission has a separate central-review.md triage. Full
implementation/evidence review and remaining caller adoption stay open.

Performance follow-up is bounded investigation; no new timing is claimed for the
installed full release. Replacing output hashing with a record digest would not
preserve product-byte integrity. Automatic cache defaults and retirement remain
release decisions, not silently implemented migrations.

The completed [preparation audit](../2026-10-14-preparation-followup/report.md)
measures 5,000 small synthetic task hashes at median 0.419s, supporting a modest
CPU cost rather than a dominant SQLite bottleneck. A same-size/restored-mtime
corruption control proves record-digest reuse cannot replace product hashing.
MaxSS output checks originate in its explicit acceptance helper, not automatic
run_lock resolver hashing. No new full-release throughput improvement is claimed.
