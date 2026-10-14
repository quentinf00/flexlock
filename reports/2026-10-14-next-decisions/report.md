# Remaining migration decisions and executable proposals

The migration status documents now separate historical milestones from installed
0.9.2 adoption, and private materialization from a proposed public export API.
See [review decisions](../../docs/next_migration_decisions.md).

The SAR receipt validator is an isolated project-owned proposal. No SAR source,
scientific extraction, dataset assembly, installed package or artifact changed.
It validates explicit produced/empty outcomes, SAFE identity, contained product
paths, CSV hashes and row counts. The existing FlexLock output hook binds the
effective SAFE and detects later CSV corruption, without a new optional-output API.

Validation with `/tmp/flexlock-no-pandas/bin/python`:

- `pytest tests/test_sar_outcome_proposal.py tests/test_slimmer_workflow_examples.py
  -q --disable-warnings`: 20 passed, 49 existing warnings.
- Added SST-style root-propagation case checked separately: 1 passed, 9 existing
  warnings. Synthetic functions only; not actual SST preparation acceptance.

The synthetic retained-preparation case validates a completed declared producer,
shows why modifying a detached config does not rewire later stage selections, then
updates the root before selecting and executes only the downstream consumer with
smart_run=False. No expensive scientific stages or Slurm jobs were launched.

Next review: accept the project SAR receipt/assembly-path change, or adjust its
contract. Recommendation: defer public Slurm export and keep profiles/after/job-ID
submission. Actual SST retained-preparation adoption and Python caching default
changes remain open; automatic caching has not been removed.
