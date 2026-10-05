# Workflow integrity before API consolidation

The workflow lab's FEATURE_REQUESTS.md and API_SIMPLIFICATION.md prioritize
failure propagation and output health before adding orchestration or changing
the public facade. This patch addresses those two P0 items through existing
entry points, with compatibility for existing config and record schemas.

## Implemented behavior

- Failed task workers persist receipts and exit nonzero after draining their
  queue. Independent items continue; stages after a failed stage are blocked.
- Synchronous CLI/decorator runners check typed execution status before their
  legacy raw-payload return. Python submit methods retain typed result shapes.
- `_outputs_` contracts check required paths, opt-in file SHA256 baselines and
  project validators at completion and before reuse. Schema/count/coverage
  validation remains project-owned, with no new mandatory validation library.
- Reuse checks cover cache hits, skip/resume, serial/parallel sweeps, and done
  DB rows. Old runs without declarations retain their original behavior.

The patch does not introduce a second execution engine or the proposed plan /
launch / resume facade. It does not reinterpret existing skip as identity-safe
resume: exact config/code/input identity, single-owner reservation and retry
history still need the later resume contract. Required-output validation does
not certify scientific gates or uniquely bind an unpinned upstream producer.

## Acceptance evidence

`tests/test_workflow_integrity.py` exercises CLI failure/resume, standalone and
multiprocess workers, Slurm/PBS bootstraps, deleted outputs across reuse paths,
completion rejection, checksums, schema/count validators and cache relocation.
Existing pipeline/task-record tests retain their per-stage error assertions.
The full suite passed with 724 tests and one expected failure. After the final
completion-order adjustment (allowing generated `results.json` contracts), all
36 focused integrity/completion/record tests passed. Logs live under
`/jobscratch/qfebvre/flexlock-hpc-chaining/p0-{full,completion}-tests.log`.

`tests/slurm_failure_acceptance.py` is an explicit opt-in live CPU test. It
submits a failed producer and an afterok consumer, checks accounting and absence
of consumer execution, then cancels the blocked consumer. The first attempt
(jobs 354473/354474) stayed pending for three minutes; both were cancelled.
Local bootstrap acceptance passed, but live scheduler failure acceptance remains
pending. Evidence: `/jobscratch/qfebvre/flexlock-p0-slurm-20261004/acceptance.json`.

Next: explicit project registry and uniform item/status contracts, then pure
planning and one launch/resume kernel beneath compatibility wrappers. Scheduler
profiles remain useful; automatic heterogeneous graph compilation stays a
separate experimental feature until its evidence contracts are demonstrated.
