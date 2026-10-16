# Central review — 260617_biomass--biomass_proc

## Acceptance decision — 2026-10-14

**Decision: accepted — bounded retained-wave selection/reassessment, with explicit
file-based source evidence exception.**
Independently verified both declared outputs/completion markers and all 23 captured
source-file hashes. Recomputed the saved prediction RMSEs: 1.604877006434514 m/s,
0.35760296173506734 m Hs, 1.110787557196596 s T01; all match the assessment. Confirmed
24,594 rows/1,604 acquisitions and inspected the selection/assessment/source checks.
The local JUnit receipt records 27 tests, zero failures/errors/skips. This review
accepts the retained recipe, not every frozen production pipeline branch based only
on that receipt. Source hashes/scoped diff are a declared narrower evidence contract,
not a whole-repository snapshot or proof of external producer environments.
Keep that exception visible; the core currently stages the entire dirty checkout
and merely stores include/exclude as comparison metadata. Do not enable auto-source
snapshot over the 20 GB arrays until a safe scope policy is reviewed. Full producer
execution, subprocess drift and broad archive/scientific compatibility remain open.

Local project feedback is mirrored in `reports/flexlock-adoption/central-feedback.md`.

## Release/follow-up status — 2026-10-16

The reviewed scoped capture policy shipped in 0.9.3. A bounded fresh source
record with the explicit Biomass scope passes capture/comparison equality checks;
this does not rewrite the retained-wave recipe's historical file-evidence exception
or certify subprocess model provenance. The project owner's dependency repair
was preserved during the successful runtime upgrade.

See [rollout evidence](../../2026-10-15-release-rollout/report.md) and
[unreleased follow-up](../../../docs/project_feedback_followup.md).
