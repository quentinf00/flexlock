# FlexLock campaign launcher proposal

A project-owned Python script describes a campaign, and a small shared helper submits its stages through FlexLock, records Slurm job IDs, and shows enough status for another session to pick up the work. Start with MAXSS-NF’s B-CONV campaign, where four GPU fits feed one CPU scorer.

## Example campaign

The following sketches the proposed helper API. The project supplies its existing fit and score configs and CPU/GPU profiles.

```python
with Campaign.open(run_root / "b-conv.jsonl", order="B-CONV") as campaign:
    fits = [
        campaign.submit(
            key=f"{arm}/shard-{shard}",
            config=make_fit_config(arm, shard, run_root),
            slurm_config=GPU_PROFILE,
        )
        for arm in ("adam400", "oc200")
        for shard in (0, 1)
    ]

    campaign.submit(
        key="score",
        config=make_score_config(
            run_root,
            fit_dirs=[fit.save_dir for fit in fits],
        ),
        slurm_config=CPU_PROFILE,
        after=fits,
    )
```

The helper calls `Project.submit(..., wait=False)`. It passes the accepted fit job IDs as `after=`, and the score config binds the exact fit directories. Slurm releases the scorer after the dependencies succeed. The scorer checks the frozen cohort and expected outputs before comparing the arms. The project's order can link to the ledger. [Existing FlexLock chaining example](../examples/slimmer_workflows/orchestrate.py) · [Submission and recovery behavior](../docs/slurm_submission_workflow.md)

## Ledger and status

For each submission, record the stage key, attempt, concrete destination, dependency IDs, and accepted job ID. Persist the submission intent before calling FlexLock and the acceptance receipt as soon as the ID is available. Resume under a single writer for the ledger and verify that the requested stage matches the recorded submission before reusing its receipt.

A status command reads the ledger, Slurm state, and FlexLock records. For example:

```text
$ campaign status /shared/runs/b-conv/b-conv.jsonl

adam400/shard-0   Slurm COMPLETED   FlexLock SUCCESS
adam400/shard-1   Slurm COMPLETED   FlexLock SUCCESS
oc200/shard-0     Slurm COMPLETED   FlexLock SUCCESS
oc200/shard-1     Slurm TIMEOUT     Fit output incomplete
score             Blocked by oc200/shard-1
```

- **Interrupted launch.** If three submissions have recorded receipts and the fourth was never attempted, rerunning the launcher reuses those receipts and submits the remaining work.
- **Uncertain acceptance.** If the ledger has an intent without a receipt, reconcile the job against Slurm before retrying that stage. This covers a crash after Slurm accepted the job but before its ID was recorded.
- **Confirmed fit failure.** Submit a fresh attempt for the failed shard when authorized. Create a fresh scorer bound to the three retained fits and the replacement, with dependencies on any producers still in flight. Keep the earlier attempt and its evidence in the ledger.

## First version

Cover chain submission, read-only status, and resuming interrupted submissions. Use B-CONV as the example and check the interrupted and uncertain-acceptance paths with a fake scheduler before trying a live campaign. A future Prefect flow could call the same helper for unattended monitoring.

The [slim-core draft](slim-core.md#3-sweeps-why-agents-dont-use-them-and-what-changes) also proposes mixed-resource sweeps and persisted scheduler IDs. Before promoting this helper beyond a project example, check whether that work covers the same fan-out and scoring needs, and reuse its submission records if available.
