# Slurm submission workflow — proposal for review

2026-10-06. Current API described below is available in the isolated checkout.
Prepared-launch commands are design sketches, not implemented flags.
[Workflow recipes](workflow_guidelines.md) and [migration plan](slimmer_core_migration.md).

Keep two ordinary inputs: a computation config and a Slurm profile. Keep --after as
a narrow afterok convenience and --print-job-id for small project scripts. Expose
scheduler-specific options through Slurm rather than duplicating its entire CLI.

## Current profiles, dependencies and held jobs

```yaml
# slurm/cpu.yaml — adapt partition/environment paths to your cluster
startup_lines:
  - '#SBATCH --partition=cpu'
  - '#SBATCH --cpus-per-task=4'
  - '#SBATCH --mem=16G'
  - '#SBATCH --time=01:00:00'
  - 'cd /shared/checkouts/myproject-pinned'
python_exe: /shared/envs/myproject/bin/python
```

A GPU profile changes partition, GPU request, memory and environment. A bounded
CPU pool profile adds #SBATCH --array=0-7. Put all #SBATCH lines before shell
commands: directives after a shell command are ignored. The example allocates
resources only; it does not arrange distributed training processes.

For held jobs today, add '#SBATCH --hold' among the profile directives, then submit
with --print-job-id (or Python wait=False). Review with scontrol show job JOBID and
release with scontrol release JOBID. A hold affects eligibility, not success or data
binding. Held jobs still occupy a destination and must count as active launches.
[Slurm hold behavior](https://slurm.schedmd.com/sbatch.html#OPT_hold),
[release command](https://slurm.schedmd.com/scontrol.html#OPT_release).

--after JOBID[:JOBID...] remains. It means successful completion of these scheduler
jobs, not inference about artifacts. Use the corresponding explicit producer paths.
Conflicting dependency directives in the profile are rejected when using --after.
The current unpinned run/newest lookup under --after is compatibility behavior;
the slimmer-core recipe uses a concrete producer, including a predetermined future
path. A failed producer blocks the downstream allocation; inspect/cancel it rather
than treating SUBMITTED as success. Slurm's dependency lookup retention window also
means very old successful jobs should be represented by validated artifacts, without
reusing their scheduler IDs. [Dependency semantics](https://slurm.schedmd.com/sbatch.html#OPT_dependency).

## Distinguish preview, preparation and submission

| Operation | Local writes | Scheduler call | Meaning |
|---|---|---|---|
| Existing --print-config / --dry-run | No launch queue/payload written | None | Inspect configuration or a script with a placeholder payload |
| Proposed --prepare-job BUNDLE | Compiled config, queue/task pickle, real script, manifest and destination claims | None | Ready-to-submit invocation; not a submitted job |
| Existing normal submission | Same materialization, then launch | sbatch | Scheduler accepted a job; ID recorded; completion separate |

An existing dry-run script names a placeholder pickle. Copying its stdout to a file
and calling sbatch is therefore not a runnable export. --enqueue exports computation
entries; it also does not materialize a Slurm launch.

The proposed prepare operation should use the same path as normal submission, with
normal submit implemented as prepare then submit. Avoid another serialization or
record format. A prepared launch is ordinary invocation/queue membership plus a
scheduler script; it is not a general execution plan or a pipeline object hierarchy.

A bundle contains task.pkl (or the existing worker payload), job.slurm, the existing
queue and compiled configuration, and a small submission manifest: absolute paths,
working directory, interpreter/environment, source/input identity, dependency IDs,
script/payload digests, destination claims and an argv list for sbatch. The printable
command is correctly shell-quoted; programmatic callers use argv, never eval.
Pickling preserves callable configuration, not a frozen installed environment/code.
Do not mark task computation complete, submitted or cached just because preparation
succeeded; prepared queue entries remain pending until workers execute them.

Proposed CLI shape:

```bash
# PROPOSED, not available yet
flexlock-run -d myproject.configs.run.cfg -s train \
  --slurm-config slurm/gpu.yaml --after 12345 --prepare-job /shared/launches/train001
# Prints a real command, with a fixed working directory and absolute script path:
sbatch --parsable --chdir=/shared/checkouts/myproject-pinned /shared/launches/train001/job.slurm
# One-off scheduler options go BEFORE the script path:
sbatch --parsable --hold --time=02:00:00 \
  --chdir=/shared/checkouts/myproject-pinned /shared/launches/train001/job.slurm
```

Slurm command-line options override environment/script settings. Record the actual
command and the scheduler's accepted settings, not just the profile defaults.
--parsable can return ID;cluster, so machine parsing must preserve/handle that form.
[Option precedence and ID output](https://slurm.schedmd.com/sbatch.html).

## What a raw manual sbatch call gives up

Manual sbatch is useful, but FlexLock cannot observe the call or learn its job ID
until someone reports it (or the worker starts). A held job can remain invisible to
the controller for days. A printed command alone cannot provide reliable queued-job
tracking, final scheduler parameters or submit-time failure bookkeeping.

Prefer one small bundle submission helper, rather than an argument per Slurm option:
proposed `flexlock-submit BUNDLE -- --hold --time=02:00:00`. It verifies digests and
claims, invokes sbatch with an argv list, and records the returned scheduler ID and
actual arguments. Exact command/API naming is still open. A backend prepare() method
and its submit() wrapper should share this path.

Raw manual submission remains possible, with an explicit project launch ledger and
a proposed attach/record-ID operation; until attached, the library must expose its
scheduler state as unknown. Avoid inventing a job ID at preparation. Capture stderr
on failed submissions and retain the bundle for diagnosis. If attaching after a
manual launch fails, inspect the accepted job before retrying any submission.

Do not promise that arbitrary appended options preserve the invocation contract:
changing chdir/export/interpreter, replacing dependencies or adding an array changes
execution. The helper should reject contradictory generated dependency settings
and repeated bundle submissions. Reviewed resource/hold/account options are the
normal escape hatch; more advanced raw Slurm use is project-owned and must retain
the actual settings. No need for --hold as another top-level FlexLock flag initially.

## Destination claims and delayed launch

Preparation should check and claim destinations before returning the command.
Otherwise another launch can occupy them between export and manual submission,
forcing a worker-time collision. Claims survive while a job is held or the bundle
is awaiting submission. Discarding an unsubmitted bundle explicitly releases its
claims; do not auto-expire one whose submission status is unknown.

The helper checks claims before sbatch; default refusal applies to occupied records
and active/prepared launches. --force must not steal a pending/running/held writer.
A prepared bundle is submitted once unless an explicit continuation/recovery policy
is used. Array workers may share one launch; accidental resubmission is different.
Record these distinctions without implementing a general distributed ownership
framework. Start with one controller per campaign root and narrow atomic claims.

Freeze ordinary existing producer choices at preparation. An explicit future path
can be read at consumer start, with its required afterok relationship. If dependency
IDs are not known yet, prepare the downstream after producer submission or use the
submission helper to attach validated dependencies and record them; never substitute
a newest run. Preparing a whole graph is unnecessary for this feature.

## Implementation placement and acceptance

M1 establishes guard/active-launch contracts. M2 establishes concrete upstream
bindings. Then add the preparation split as a bounded backend change, before wider
adoption. Current draft/examples do not implement it or claim its guarantees.

Acceptance must show: no sbatch invocation during prepare; runnable payload/script;
normal submit shares preparation; shell/path quoting and cwd independence; accurate
held/submitted states; rejection before sbatch on destination collisions; failed
submission does not claim acceptance; digest mismatch/repeat launch refusal; manual
ID attachment; dependency conflicts; array worker draining; explicit disposal; source
drift detection or immutable checkout. Use fake sbatch and local worker execution
first. Retain existing side-effect-free preview behavior.
