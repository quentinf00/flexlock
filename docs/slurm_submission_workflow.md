# Slurm submission workflow

2026-10-06. Profiles, --after and --print-job-id are available in the isolated
checkout. The backend preparation seam below is proposed, not implemented.
[Workflow recipes](workflow_guidelines.md) and [migration plan](slimmer_core_migration.md).

## Ordinary use: computation config plus resource profile

```yaml
# slurm/cpu.yaml — adapt paths and partition to your cluster
startup_lines:
  - '#SBATCH --partition=cpu'
  - '#SBATCH --cpus-per-task=4'
  - '#SBATCH --mem=16G'
  - '#SBATCH --time=01:00:00'
  - 'cd /shared/checkouts/myproject-pinned'
python_exe: /shared/envs/myproject/bin/python
```

A GPU profile changes partition, GPU request, memory and environment. A bounded
CPU pool can add #SBATCH --array=0-7. Put directives before shell commands. These
requests allocate resources; distributed training processes need project setup.

Keep --after JOBID[:JOBID...] as an afterok convenience and --print-job-id for
small scripts. Dependencies express scheduler ordering. Explicit producer paths
express artifact selection. A failed producer blocks the consumer; SUBMITTED
means acceptance, not completion. Old completed artifacts should be validated
without relying on indefinitely retained scheduler IDs.
[Slurm dependencies](https://slurm.schedmd.com/sbatch.html#OPT_dependency).

To hold a job today, put '#SBATCH --hold' among the profile directives. Inspect
with scontrol show job JOBID and release with scontrol release JOBID. Pending
queue entries reserve destinations even while the scheduler holds a job.
[Hold](https://slurm.schedmd.com/sbatch.html#OPT_hold),
[release](https://slurm.schedmd.com/scontrol.html#OPT_release).

## Destination guard in the supported controller path

Project submission holds POSIX advisory locks on all concrete product directories
and the queue root during controller work. Checks precede marker invalidation,
cleanup, queue writes and backend submission. Queue rows in pending/running state
reserve products before workers write run.lock; products point to their queue even
when it lives elsewhere. --force, overwrite and unsafe cannot bypass active rows.
Unknown ownership from a missing referenced queue is refused.

Existing workers may drain the queue, including multiple workers in a pool. A new
controller must not replace the same destinations or rewrite an active queue root
(even for disjoint new products), since that would replace its master provenance.
Use flexlock-worker to continue unchanged queued computation. Before recovery,
inspect queue and scheduler state; canceled or failed submissions can leave pending
rows. The guard does not infer their safety from a missing job ID or auto-expire them.
Queue mutation/reclaim is an explicit maintenance operation after old workers stop.
Completed task rows do not prove every scheduler allocation or pool worker has exited.
Stop prior workers before forced queue reuse; the guard tracks queue activity, not
the full scheduler allocation lifecycle.

Locks require cooperating controllers and a filesystem supporting flock. Direct
ParallelExecutor/queue manipulation is advanced use under the one-controller rule.
The library cannot prevent external programs from editing products or records.

Force intentionally replaces the current record and invalidates completion; it
keeps existing products for the callable to overwrite and does not archive evidence.
Sweep/pipeline force also resets their queue and result projections. Copy evidence
or choose a fresh run before replacement when historical references must remain valid.
Overwrite cleans occupied directories. Keep immutable producer paths for consumers.

## Next seam: materialize a runnable backend invocation

The existing --dry-run previews a script with a placeholder payload. Its output is
not a runnable export. --print-config and --dry-run remain side-effect-free previews.

The next bounded change should extract backend materialization: serialize the
existing worker payload, write the real scheduler script, and return their absolute
paths plus an sbatch argv list and working directory. Normal backend submit then
uses that result. Keep existing payload/queue formats; add no mandatory launch object
or pipeline compiler. Test with fake sbatch and actual local payload execution.

An advanced caller could print a shell-quoted command and insert one-off Slurm
arguments before the script path:

```bash
# Illustrative output of the future backend seam; no new CLI flag exists yet.
sbatch --parsable --hold --time=02:00:00 \
  --chdir=/shared/checkouts/myproject-pinned /shared/launches/train001/job.slurm
```

Command-line options override script/environment settings. Record actual arguments;
changes to dependencies, working directory, exports or array membership affect the
invocation, beyond resource tuning. Programmatic callers use argv rather than eval.
[Slurm options and parsable output](https://slurm.schedmd.com/sbatch.html).
Pickling a callable does not freeze its imported code/environment.

## Explicit limits of manual export

Raw sbatch is project-owned advanced use. FlexLock cannot observe acceptance, the
job ID, actual scheduler settings or repeat submissions. Do not claim that exporting
a script guarantees one submission. A crash between scheduler acceptance and
recording the ID creates uncertainty: inspect scheduler state before retrying.
Preparation success is not scheduler acceptance or computation completion.

Defer managed bundle claims, attach/record-ID/dispose commands, automatic recovery
and a public prepared-launch lifecycle. These would add coordination obligations
that are unnecessary for ordinary profile-based submission and occasional holds.
The materialization seam should be useful and testable before considering a public
CLI export. Any future managed delayed-launch feature needs its own concrete
ownership contract and acceptance evidence.
