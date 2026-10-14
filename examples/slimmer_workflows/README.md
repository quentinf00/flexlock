# Smaller-core workflow examples

Review against [guidelines](../../docs/workflow_guidelines.md) and the
[Slurm proposal](../../docs/slurm_submission_workflow.md).

- cfgmod.py/stages.py: explicit root anchors and distinct stage directories.
- bindings.py: project acceptance of completed, declared producer products.
- campaign.py: frozen input hashes, one bulk export, deliberate coverage gate.
- sar_outcomes.py: isolated per-SAFE produced/empty receipt proposal; not yet
  integrated into SAR extraction. See [remaining decisions](../../docs/next_migration_decisions.md).
- orchestrate.py: separate CPU/GPU/CPU submissions and a best-effort ID ledger.
- slurm/: template resource profiles; adapt cluster/environment paths.

Run commands from the repository root with this checkout importable. The toy
functions use small JSON inputs and exercise plumbing only. Config/queue review
does not launch a job; orchestrate.py does. Nothing here automatically migrates
production configurations or claims prepared-job support.

Validation is in tests/test_slimmer_workflow_examples.py: local chained execution,
explicit reuse, produced/empty/excluded/missing/corrupt coverage, fake scheduler
dependencies and retained ledger after partial submission failure. Guard regressions
are in tests/test_destination_guard.py. No thousand-item performance claim is made.
