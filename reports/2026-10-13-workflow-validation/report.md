# Workflow acceptance and transition review

Installed FlexLock 0.9.2 was exercised against real SST, SAR and neural-field project configurations. No retained scientific artifacts were relocated.

- SST: a fresh reassessment of frozen matchups matched the retained assessment exactly across 15,975 common platform-days. All eight retained baseline files were unchanged. No training or inference ran.
- SAR: the existing split implementation produced 22,472 training, 7,490 validation and 4,255 test members, with exact eligible membership and disjoint sets. Listing identity was unchanged. This validates existing plumbing, not scientific leakage safety: 3,973 datatakes cross train/validation in the existing split.
- SAR campaign preview: 34,218 frozen SAFE members, three preview destinations all distinct. No extraction ran. Adoption requires explicit produced/empty outcomes and a coverage gate: missing CSVs cannot stand in for legitimate empty outcomes.
- Neural-field: actual worktree configuration and installed shared environment passed signature/path checks. Retained product-benchmark files were unchanged; no training/inference ran.
- Recipes: ten acceptance tests passed, including coverage and separate-resource dependency bookkeeping.
- Slurm: actual CPU control job 1352647 completed with exit 0:0 in seven seconds; all three stages and output checks passed. Worker used the matching validation checkout. This was a single allocation, not a real CPU/GPU/CPU allocation chain.

The original Slurm frontend assumed --print-job-id returned ExecutionResult values and raised after submission. The authoritative queue and sacct confirmed completion. The corrected launcher captures CLI job IDs and requires a fresh run label; the accepted job was not resubmitted.

[Transition proposal](TRANSITION.md) inventories project starting points and proposes additive config/binding cleanup. Existing config entrypoints and artifact paths remain in place. SAR extraction outcome changes and destructive cleanup require project review before adoption.

Actual runs and full frozen membership remain under /ontap/user/qfebvre/workflow-transition-validation/20261013. Included scripts and JSON summaries document the bounded validations; they are review prototypes, not production entrypoints.
