# Central review — hafs-jepa

## Acceptance decision — 2026-10-14

**Decision: accepted — bounded retained HAFS dynamics evaluation; IRAR numerical
replay accepted with an explicit source-provenance gap.**
Inspected the actual legacy acceptance helpers and independently verified ten
declared output hashes/completion markers across both evaluations. Independently
compared all three IR prediction tables (5,151/4,301/3,513 rows), results.md and
frame_cls.npy with retained outputs: exact matches.
The IRAR run predates the explicit geo-jepa declaration. Do not claim that its
record captured geo-jepa, or retrofit historical records. Verify a fresh small
record with the explicit sibling repo before calling that provenance-complete;
this need not repeat the full evaluation. seq_emb, training and scheduler execution
remain unvalidated/deferred. Keep the adapter's historical limits explicit.
Nested-target discovery and implicit imports are different: the current core adds
only the stage's top-level target repo. The probe imports geo_jepa internally, so
its explicit declaration is appropriate even if nested-target discovery improves.
The results.json overwrite is reproduced centrally; avoid that product filename
until an approved compatibility fix ships. No proposed core API change is installed.

Local project feedback is mirrored in `reports/flexlock-adoption/central-feedback.md`.

## Release/follow-up status — 2026-10-16

The 0.9.3 rollout fixes return/product collisions and implements nested-target
repository discovery with shared capture/comparison scopes. Explicit ordinary
imports such as geo-jepa still need declarations; historical gaps remain. The
unreleased follow-up adds numeric-identifier diagnostics and the legacy-adapter
guidance; it does not infer types from annotations.

See [rollout evidence](../../2026-10-15-release-rollout/report.md) and
[unreleased follow-up](../../../docs/project_feedback_followup.md).
