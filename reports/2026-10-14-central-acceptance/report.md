# Central acceptance review — 2026-10-14

Reviewed all seven current project submissions. SAR retains its prior bounded
preprocessing acceptance. Six additional decisions and project follow-ups are
recorded beside each submission in central-review.md. Acceptance is scoped to
validated recipes; deferred callers and full scientific campaigns remain open.

Independent current-byte verification: 30 declared outputs across six projects,
all hashes and completion markers valid; 23 Biomass source hashes match. Full
machine-readable details: output-verification.json.

Additional independent checks: HAFS-JEPA IR predictions/table/embeddings match
retained results exactly; Biomass's three saved-prediction RMSEs recompute exactly;
SST's 24 rows match its reference at 1e-12; NextGEMS's gate rejects unaccepted
missing_zarr and passes only with explicit acceptance. MaxSS's mocked partial
submission preserves its accepted-ID ledger and refuses ledger replay.

HAFS-tools current zip coverage recheck exceeded the bounded review duration and
was stopped; declared receipt hashes are verified. The bounded receipt-only retry
passed v1-wind/v1-mom6 and rejected the retained wind item with 19 missing cycles.
No scheduler jobs, scientific replay,
product mutation, model fitting or project source changes were made.

Core reproductions: top-level repo discovery ignores a nested sibling target;
RunRecord.write_results(None) overwrites callable-owned results.json with
{"result": null}. Snapshot source confirms include/exclude are not passed into
whole-checkout staging. Initial overwrite assertion expected scalar null and was
corrected to the actual wrapper object; both demonstrate data loss.

Proposals and release decisions are tracked in docs/project_feedback_triage.md.
