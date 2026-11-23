# Should FlexLock exist, and in what shape (2026-11-23)

Discussion notes to pick up from. Read with [slim-core.md](slim-core.md) (the census and the
cut-down plan) and [campaign-launcher.md](campaign-launcher.md) (chains across resources).

**Working plan:** option B with Python configs kept, in [kernel-plan.md](kernel-plan.md).

## The original promise

Seamless provenance for Python scripts and functions, while keeping freedom in how they are
configured and run (locally, in parallel, on different backends).

## What the census says about that promise

- **Provenance is only seamless on the `flexlock-run` path, and agents leave that path for about half
  of the work.** Multi-run campaigns: shell loops over `flexlock-run` (≈13 of about 35), custom
  launchers (≈6), raw sbatch or arrays (≈7), `Project.submit_pipeline` per arm (sst), the sweep API 2.
- **Raw Slurm arrays are used for data preparation, not inference:**
  - TC-PRIMED caches, one year per task (`--array=1987-2024%8`, hafs-jepa, Nov 17);
  - the cross-track cache (`--array=2005-2024%8`, Oct 21);
  - GridSat downloads and the V07 build per month (tcwind_benchtools, Nov 19–20).

  Inference campaigns went through FlexLock, as loops of `flexlock-run`; one storm inference
  ran as a sweep and worked. No transcript states why an array was chosen. Inferred reasons:
  - the work is a plain script, not a `flexcli` stage;
  - many tasks write shards of one dataset, which clashes with one run dir per item and the
    destination guard;
  - arrays give throttling (`%8`), per-index logs and one job id in one line;
  - FlexLock sweeps have no visible throttle, contradictory `n_jobs` docs, and overwritten logs.
- **When agents skip FlexLock, they rebuild provenance by hand.** The TC-PRIMED job copies its
  script into the output folder and `cmp`s it at job start. sst built `source_guard.py` because
  FlexLock captures source at worker start, not at submission. The need is real; the tool's
  coverage is the problem.
- **Chains across resources** (GPU train → CPU probe, each `--after` its own parent) are not served:
  agents write ledgers and launchers by hand (see campaign-launcher.md).

## FlexLock against the alternatives

Comparisons are from general knowledge of these tools, not tested here.

| Need | FlexLock | Closest alternative | What the alternative leaves out |
|---|---|---|---|
| Python configs, `instantiate` | `py2cfg`, `flexcli` | Hydra / hydra-zen | little; FlexLock duplicates it |
| Submit Python callables to Slurm, arrays, job ids | own Slurm backend, pickles, workers, SQLite task DB | submitit (arrays, per-job logs, no database) | little; FlexLock reimplements it, and its worst bugs live here |
| Sweeps | sweep API (rarely used) | Hydra multirun + submitit launcher; Snakemake wildcards | — |
| Chains on mixed resources | `--after`, hand ledgers | Snakemake (per-rule resources, Slurm executor), Prefect (DAGs, retries, UI), Nextflow | FlexLock does not solve this today |
| Per-run provenance (git tree + diff, config, environment, input hashes, upstream runs) as files in the run dir, no server | **yes: the core** | DVC (content-addressed, in git), ClearML / W&B / MLflow (git diff and args, on a server), Hydra (`.hydra/` config only) | no single tool gives this combination |
| Never overwrite a result; outputs bound to the record | destination guard, `validate_outputs` | DVC (by content) | — |
| Records readable as plain files by agents, XPCC and ACDM | yes | the others keep them in a server database or in git | — |

Why the obvious replacements fall short here:
- **DVC:** hashing terabyte zarr stores, a lock file in git while many experiments run in parallel,
  and no Slurm executor.
- **ClearML / W&B / MLflow:** the provenance lives on a server. Agents, XPCC and ACDM read records
  from the filesystem, and compute nodes would depend on reaching the server.
- **Prefect:** good at chains, retries and state, but records nothing about code or data. It needs a
  long-lived server and worker on the cluster (a login-node daemon, or a worker as a Slurm job).
  It would replace a campaign launcher, not FlexLock.
- **Snakemake:** fits HPC well for chains (per-rule resources, wildcards, native Slurm), but its model
  is "files are targets", not "run dirs with a record".

**For keeping FlexLock:** the run record is the one thing no tool gives in this setting, and the
whole system now depends on it: XPCC attempts, the tick, triage, and ACDM's runs sensor read
`run.lock`/`run.complete`. Agents rebuild it by hand whenever they bypass FlexLock.

**Against FlexLock as it is:**
- about 14,700 lines with one maintainer, most of it reimplementing Hydra, submitit and part of DVC;
- the worst bugs sit in the reimplemented parts (SQLite task DB and hash cache on NFS, log overwrite);
- agents bypass it for data prep and chains;
- sst had to patch the core promise (source captured at submission).

## Options

| Option | What it means | Cost |
|---|---|---|
| A. Slim | [slim-core.md](slim-core.md): keep the execution engine, sweeps and record; drop query, inspection CLI, mlflow, PBS. About 9,600 lines | moderate; keeps owning the Slurm backend and task DB |
| **B. Provenance kernel** (proposed) | Keep only what no tool gives; delegate execution | larger API change for projects; much less to maintain |
| C. Drop | Hydra + submitit + a tracking server or DVC | loses the file-based records XPCC and ACDM rely on; migrates 4 projects |

### B in detail

Keep (my estimate: 2,000–3,000 lines):
- **The run record**, in the `.flexrun/` layout of slim-core.md §4: git tree and diff **captured at
  submission**, config, environment lock, input references and hashes, upstream runs, outputs
  manifest, markers (`run.complete` stays visible).
- **The destination guard** and `validate_outputs`.
- **The minimal reader** (`load_record`, task records, `status()`) and `flexlock status <run>`.
- **`flexlock record -- <any command>`:** wraps a plain script, inside any launcher (raw arrays
  included), and writes the same record as a stage. This closes the data-prep gap.
- `py2cfg` and `flexcli`, if the project's config style is worth keeping; otherwise a thin layer
  over hydra-zen.

Delegate:
- **Submitting Python callables and arrays → submitit.** Replaces the Slurm backend, pickles,
  workers and the SQLite task DB, and with them the corruption failures.
- **Sweeps → an array over items,** each item wrapped by the kernel.
- **Chains → the small campaign launcher first** (ledger + `after=`, campaign-launcher.md). Then
  Snakemake if chains keep growing. Prefect only if a dashboard with retries is wanted despite the
  server it needs. The XPCC board and tick already cover monitoring.

## Next steps

1. **Fix now, whatever the direction (0.10.2):** unique Slurm logs (`%x-%j`), files written 0644,
   the hash cache off SQLite WAL on NFS (quarantine and rebuild on "malformed"), `run.complete` on
   sweep roots, `flexlock --version`. Details in slim-core.md §4.
2. **Experiment 1, the record wrapper:** write `flexlock record --` and use it on a TC-PRIMED-style
   array. Check that it writes the same record a `flexlock-run` stage does, and that XPCC and
   ACDM read it.
3. **Experiment 2, chains:** run B-CONV (four GPU fits → one CPU scorer) twice: once as submitit +
   kernel + campaign launcher, once as a Snakemake rule set. Compare the effort, the job ids and
   ledger, and what XPCC can read.
4. **Decide A, B or C** using the wrapper, chain and [Python config replay](#an-experiment-before-adopting-b)
   experiments. Then revise slim-core.md's release table accordingly.
5. **sst, independently:** settle its 198 uncommitted files first (last commit 2026-09-08); the rest
   of its migration (slim-core.md §5) waits on the direction.

## Recommendation for B — keep Python configs, `py2cfg` and `flexlock-run`

Keep these three as first-class interfaces and delegate scheduling. A researcher can define
`cfg` in an ordinary Python module, import it, derive another config from it, and launch it
directly. For example, `flexlock-run -d experiments.baseline.cfg -s train -o width=256`
needs only an importable config object. The project author can launch it without registering it.

The reason to keep `py2cfg` is visible months later. Given a checkpoint, a reader can inspect
the training function, the nested encoder constructor and the width passed to it. The top-level
source record identifies the captured trees containing those implementations. A shell command
alone would generally leave the reader to reconstruct those choices from the script. Even if
literal replays are rare, a record precise enough to replay answers everyday provenance questions.

### How the runner would work

1. **Prepare the call.** Import the named config object, apply merges and overrides, and select
   the stage. Keep `--print-config` for inspecting the result. Save the module attribute, stage
   and overrides as the origin, alongside the call description produced from `py2cfg` (target,
   arguments and nested targets). Capture the declared source trees at submission, covering both
   the config definition and the callable implementations. Bind available upstream inputs and
   record the concrete values used when a queued dependency becomes available.
2. **Run from the prepared record.** Locally, invoke the prepared call directly. With
   `--slurm-config`, have a submitit adapter hand the worker a path to that record. The worker
   reads the saved call and imports its targets. Later edits to the author's config therefore
   cannot change a queued job's arguments. The adapter owns submission and job IDs. FlexLock owns
   the destination guard, input and source provenance, output validation and completion marker.
3. **Replay into a fresh destination.** Let `flexlock-run` read the saved call even after the
   original config attribute has been renamed. Preserve concrete input bindings. Account for
   every declared output when changing destinations, including absolute checkpoint paths that
   still point into the original run. Surface ambiguous paths for explicit override. The target
   name and arguments recover the call. Reproducing its historical implementation also requires
   the recorded source, environment and inputs. Report source drift when the checkout differs.

### Where Hydra fits

Keep the kernel callable from plain Python. Hydra can own composition, overrides, nested
instantiation and multirun. A thin `flexlock-run` can import the selected module attribute and
pass it to Hydra. For new configs, hydra-zen's `builds(..., populate_full_signature=True)`
is a candidate for capturing callable defaults. Its `launch` accepts a Python config object
and uses Hydra's in-memory ConfigStore internally. Registration stays out of project modules.
Check compatibility with an existing `py2cfg` stage that uses `_snapshot_`, `_outputs_` and
upstream references before changing the authoring API.
[hydra-zen builds](https://mit-ll-responsible-ai.github.io/hydra-zen/generated/hydra_zen.builds.html) ·
[hydra-zen launch](https://mit-ll-responsible-ai.github.io/hydra-zen/generated/hydra_zen.launch.html)

Offer a callback for existing Hydra apps. It can capture source on the controller at multirun
start and record each job's effective config and outcome on the worker. A generic `main(cfg)`
exposes that invocation. Recording a nested training call requires the app to describe it.
For FlexLock-managed runs, put the destination guard and output validation in the task wrapper
so a failure stops the job. Hydra converts ordinary callback exceptions to warnings.
[Hydra callback lifecycle and error handling](https://hydra.cc/docs/experimental/callbacks/)

Try the stock Submitit launcher for independent sweeps. It sends per-item overrides to workers,
loads the sweep config there, and waits for results. A source snapshot taken before the sweep
therefore leaves two questions open for campaigns: which concrete call was accepted for each
arm, and when can the caller get its job ID to submit a dependent scorer? Compare a small
direct Submitit adapter on those requirements.
[Hydra Submitit launcher implementation](https://github.com/facebookresearch/hydra/blob/main/plugins/hydra_submitit_launcher/hydra_plugins/hydra_submitit_launcher/submitit_launcher.py)

### What to borrow from Exca

Exca lets a project configure a task as a Python object, execute a decorated method locally or
on Slurm, and cache its result. That model is a good candidate for preprocessing that wants
per-item caching. For existing FlexLock projects, keep accepting ordinary research functions
and borrow three design choices. These observations come from the docs and examples.
[Exca overview](https://github.com/facebookresearch/exca)

- **Execute the captured source.** Exca's optional `WorkDir` copies selected files or editable
  packages at submission and runs the job from that directory. For FlexLock, share one captured
  tree across an array and record which tree each worker used. Include declared non-Python
  files such as YAML alongside imported helpers.
  [Exca workdir guide](https://facebookresearch.github.io/exca/infra/howto.html)
- **Distinguish a call from an attempt.** Exca saves the full config and the subset of fields
  used for cache identity. For FlexLock, retain the resolved callee and arguments for comparison
  and replay. Give each execution its own record of source, inputs, resources and outputs.
  Matching arguments alone are insufficient evidence to reuse a checkpoint.
  [Exca cache layout](https://facebookresearch.github.io/exca/infra/tutorials.html)
- **Support a Python loop over named arms.** Exca's `job_array(max_workers=...)` batches
  configured objects and exposes job handles after submission. A small FlexLock Python API
  could return each arm's job ID and run directory immediately, so the B-CONV launcher can
  bind its scorer to the four fits. For shared datasets, borrow `MapInfra`'s explicit item
  identity: record the year or shard key so retries remain traceable if array indices change.
  [Exca array example](https://facebookresearch.github.io/exca/infra/introduction.html) ·
  [MapInfra tutorial](https://facebookresearch.github.io/exca/infra/tutorials.html)

### An experiment before adopting B

Use two named arms from one existing `py2cfg` module. Establish the expected calls locally,
then compare Hydra multirun with a short Python loop using Submitit. For each path, record how
much project code it takes to cap concurrency, obtain each job ID before completion, and find
the corresponding run directory.

While the jobs are queued, edit a config argument, an imported helper and a YAML file the
stage reads. Check the actual outputs against the submitted values and source. Deliberately
omit a required output in one arm and confirm that it fails without a completion marker.
Rename the config attribute and replay the successful arm from its record into a fresh
directory. Verify the nested arguments and upstream bindings, check that the original outputs
are intact, and read both attempts through the existing reader. Use the result to decide how
much launcher code FlexLock needs to own.
