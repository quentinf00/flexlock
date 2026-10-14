# SAR preprocessing adoption — central review

2026-10-14. **Accepted for the bounded enhanced preprocessing recipe.** This is
acceptance of its local workflow/fixture evidence, not full project migration,
scientific split certification, Slurm validation or production readiness.
The separate FLEXLOCK-LIFECYCLE task remains open: no lifecycle report has been
submitted here yet.

## Evidence reviewed

- Central `report.md`, local adoption report, caller inventory/coverage,
  implementation/config, acceptance tests and logs.
- Independently recomputed all 12 hashes in `validation-summary.json`: five
  implementation/test files, three dataset outputs and four producer records
  still match the submitted evidence.
- Independently ran the read-only project coverage gate with the actual enhanced
  interpreter against `/tmp/sar-flexlock-acceptance-cuchyvku/run/extract/bindings.json`:
  ready=true, four produced SAFEs, one explicit empty SAFE, zero issues.
- Inspected selected dataset lineage: test assembly records the concrete extraction
  producer, requested bindings field and materialized producer-record digest.
- The retained test log establishes 16 passing acceptance checks in 67.933 seconds.
  These exercise real small NetCDF extraction/assembly, corruption and incomplete
  cohort rejection, and binding recovery. The full suite was not repeated for this
  review; source hashes match the tested submission.

## Accepted scope

The new `sar_ml.pipelines.preprocessing_cfg.cfg` recipe uses fresh absolute roots,
frozen membership/protocol, exact database/task bindings, independent SAFE and
partition records, and authoritative queue/result/CSV checks inside each reducer.
Strict read/feature failures are opt-in for the new recipe; legacy defaults remain
compatible. Produced/empty outcomes live in queue results, without mandatory
per-item JSON receipts. CSV checks include identity, SHA256 and row counts, so
deleted output cannot become an accepted empty outcome. Every assembly rechecks
the cohort rather than trusting a stale coverage report.

The bounded dataframe comparison supports preservation of preprocessing for the
fixture and controlled RNG seed. It does not establish equivalence of historical
datasets or leakage safety. Separately submitted local stages and retained-input
CLI reassessment are supported by the evidence. Slurm profiles and asynchronous
binding recovery are implemented but scheduler execution was not validated.

## Follow-up

1. **Core defect:** direct multi-stage CLI selection resolves downstream
   `_stages_[3]._snapshot_.data.bindings` before its producer exists. The traceback
   is retained in local `cli-chain.log`. Track a core regression and fix; retain
   the sequential project controller until a corrected release is verified.
   Do not remove input snapshots to make the chain run.
2. **CLI ergonomics:** sweeps with mandatory root `run_dir=???` require a concrete
   base override before selection in the tested recipe. The successful preview
   demonstrates explicit per-item seeds and destinations; it does not resolve the
   missing-anchor failure. Audit/reproduce separately before proposing API changes.
3. **Evidence retention:** live fixture products and queues are under `/tmp`.
   Durable local logs and selected-record exports exist, but replay depends on
   those live paths. Document retention or make an explicit archival plan before
   deleting them; summaries do not constitute a relocated executable producer.
4. **Documentation:** the local report's statement that the central report was not
   placed is now stale: `report.md` is present and this review records receipt.
   Some earlier TODO/core decision text still calls the strict-error decision
   pending; the submitted implementation records it as selected on 2026-10-14.
5. **Extended lifecycle:** proceed with the assigned dataset/collocation,
   experiment, portable release and batch inference task. Explicitly audit source
   coverage for separately versioned feature/inference packages; target-repository
   discovery alone does not prove all imported dependencies were captured.

Training/export, collocation/validation, diagnostics/MLflow, original SAR and
fix_colloc callers are explicitly deferred. Keep these open; accepting this recipe
does not close them or the extended lifecycle task. The SAR owner may record this
bounded acceptance on its local board, retaining those broader follow-ups.
