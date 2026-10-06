# Workflow guidelines for the smaller FlexLock core — review draft

2026-10-06. Review alongside the [M0–M5 migration plan](slimmer_core_migration.md).
Examples use the current isolated implementation after ebc6d92. Proposed scheduler
preparation is marked separately; it is not an available CLI option. No production
migration or job launch is performed by these documents.

FlexLock configures, executes and records a callable. The workflow selects retained
products, decides whether preparation still suits a changed model, and checks cohort
coverage. A successful invocation is evidence that it finished and passed declared
output checks. The project decides whether its result answers the scientific question.

## Organize choices as track / arm / run

Use these as plain project names, not FlexLock object types:

| Name | Meaning | Example |
|---|---|---|
| Track | A question or campaign with a stable comparison/coverage protocol | intensity-balanced |
| Arm | A named alternative compared within that track | natural, weighted |
| Run | One concrete execution of an arm with explicit upstream choices | 20261006-seed3 |

One run may contain separately recorded prepare/train/assess stages. Every fresh
invocation gets its own stage directory. If retaining preparation, point the new
run at the old preparation record rather than copying it or manufacturing a new
record. Repeated seeds and checkpoint continuation get distinct run names.
Names are human labels; provenance supplies identities. Keep a short track README
or bindings file for decisions and exclusions that a config cannot explain.

```text
project/
  configs/
    stages.py                # py2cfg stage constructors/defaults
    tracks/intensity.py      # question, protocol and named arms
    runs/seed3.py             # explicit upstream selections and run label
  slurm/cpu.yaml
  slurm/gpu.yaml
  workflows/chain.py
  workflows/check_coverage.py
  manifests/files-v1.json     # explicit membership and exclusions
  runs/intensity/natural/20261006-seed3/
    prepare/run.lock
    train/run.lock
    assess/run.lock
```

Start with one cfgmod.py. Split by responsibility when it becomes hard to read;
do not introduce config groups/defaults/store registration solely for organization.
Python imports and shallow dictionaries often suffice. Share constructors and
algorithm defaults; keep concrete producer choices in the run binding layer.
Resource profiles describe allocations/environment, rather than scientific variants.
The tree above is optional and need not match existing project paths.

## Python configuration and explicit upstream arguments

[Executable toy config](../examples/slimmer_workflows/cfgmod.py) uses this pattern:

```python
from flexlock import py2cfg
from myproject.stages import train

cfg = dict(
    runs_root='/shared/project/runs',
    track='intensity', arm='natural', run='20261006-seed3',
    run_dir='${runs_root}/${track}/${arm}/${run}',
    upstream_run='/shared/project/runs/preparation/base/20261001/prepare',
    train=py2cfg(train,
        save_dir='${run_dir}/train',
        input_path='${run_lock:${upstream_run},config.output_path}',
        checkpoint_path='${run_dir}/train/model.pt',
        _snapshot_=dict(
            repos=dict(main=dict(path='/shared/checkouts/myproject-pinned')),
            prevs=['${upstream_run}'],
            data=dict(dataset='${run_lock:${upstream_run},config.output_path}')),
        _outputs_=dict(model=dict(path='model.pt', sha256=True))),
)
```

Put the concrete producer in one root anchor and read related facts from its record.
Avoid duplicating dataset path, normalization and model settings in every consumer.
A small project helper can expose a dataset/checkpoint binding when several values
belong together. It should require a named record, check its schema and return plain
values/config nodes; it should not search for a replacement silently.
Facts describing a checkpoint should be validated against the checkpoint contents.
A record is not proof of compatibility between grids, masks or model architectures.

The resolver is run_lock; recorded callable arguments are below config. Keep the
explicit prevs declaration during migration: direct run_lock reads do not yet provide
all automatic lineage guarantees planned in M2. Hash files/manifests deliberately.
For huge datasets, document immutable version/manifest identity and its assumptions;
do not claim a weak directory metadata cache verifies all nested content changes.

```bash
flexlock-run -d myproject.configs.runs.seed3.cfg -s train \
  -o upstream_run=/shared/project/runs/preparation/base/other/prepare --print-config
flexlock-run -d myproject.configs.runs.seed3.cfg -s train \
  -o upstream_run=/shared/project/runs/preparation/base/other/prepare run=seed3-other
```

Use -o for root bindings before selection and -O for selected callable arguments.
Previewing displays deferred expressions; existing-run --check resolves them.
For a promised producer that does not exist yet, inspect the known paths and the
scheduler script; a pre-launch full --check cannot read the missing record.

For a sweep, give every item a distinct destination as well as a producer:

```yaml
# alternatives.yaml
- upstream_run: /shared/prepared/A
  run: seed3-A
- upstream_run: /shared/prepared/B
  run: seed3-B
```

```bash
flexlock-run -d myproject.configs.runs.seed3.cfg -s train --sweep-file alternatives.yaml
```

The CLI also accepts --sweep 'upstream_run=A,upstream_run=B', or --sweep A,B
--sweep-target upstream_run. Those alone do not make distinct output locations;
include output/run changes in dictionary items or apply an explicit naming scheme.
Bare stage arguments retain stage scope; main.x/train.x explicitly addresses the
selected stage through the root. Root-only anchors apply before stage selection.
@ node replacement remains useful for model/data variants; the selected concrete
upstream should remain visible in the run config. See [CLI scope](cli_reference.md).

## Fresh local/debug execution, then Slurm

Use the same callable/config. Change the input size, run label and allocation
explicitly for smoke checks. Keep smoke/proxy/full input selections identifiable.

```bash
flexlock-run -d examples.slimmer_workflows.cfgmod.cfg -s prepare train assess \
  -o runs_root=/tmp/flexlock-demo run=local001
# Select only the stage being debugged, using its chosen existing upstream.
flexlock-run -d examples.slimmer_workflows.cfgmod.cfg -s train \
  -o upstream_run=/tmp/flexlock-demo/baseline/linear/local001/prepare \
     runs_root=/tmp/flexlock-demo run=debug001 --debug
```

The stage callable writes inside its save_dir and fails clearly if inputs are
invalid. Declare required outputs when practical. An empty successful result
should have an explicit empty outcome, not masquerade as a missing product.
Avoid automatic cache checks in the fresh recipe: CLI caching is opt-in; Python
Project.submit currently defaults smart_run=True, so pass smart_run=False.

Choose a fresh directory by default. --force is intentional in-place re-execution,
not ordinary pipeline continuation. The current implementation removes completion
markers but does not archive all old evidence or protect every queued destination.
The migration must establish refusal before scheduler submission and define force
against active work; guidelines do not replace that guard. Retain old records until
that contract is implemented. An immutable code checkout/environment avoids source
drift between submission and execution; pickling a function does not freeze imports.

## File-list campaign with project coverage checks

Freeze a manifest once, recording stable item IDs, concrete input identities,
processing/exclusion decisions and reasons. Assign one output/record directory per
item. Do not start from a fresh glob at reduction time. For listing extension, make
an explicit delta manifest; document which previous item products are retained and
why. A reducer can read a project bindings file mapping expected IDs to exact earlier
or new records, without requiring a FlexLock artifact class.

```json
[
  {"item_id": "file001", "input_path": "/shared/input/001.json", "sha256": "...", "disposition": "process"},
  {"item_id": "file002", "input_path": "/shared/input/002.json", "sha256": "...", "disposition": "process"},
  {"item_id": "file003", "disposition": "excluded", "reason": "outside agreed date range"}
]
```

[Project helper example](../examples/slimmer_workflows/campaign.py) exports one YAML
list of complete configs in a single pass. It avoids thousands of individual CLI
calls or repeated YAML append/rewrite. The example computes SHA256 for small toy
files; real projects can use validated immutable input manifests instead.

```bash
python -m examples.slimmer_workflows.campaign export manifests/files-v1.json \
  /shared/project/runs/files/base/campaign001 queue.yaml
flexlock-run --sweep-file queue.yaml --sweep-root /shared/project/runs/files/base/campaign001 \
  --slurm-config slurm/cpu-pool.yaml --print-job-id
flexlock-status /shared/project/runs/files/base/campaign001/run.lock.tasks.db --watch
# After workers stop, write an explicit coverage report. Nonzero means no reduction.
python -m examples.slimmer_workflows.campaign check manifests/files-v1.json \
  /shared/project/runs/files/base/campaign001 coverage.json
```

A Slurm array profile can start a bounded pool of workers; each worker claims queue
items. --n_jobs governs local worker count; it does not create that many Slurm jobs.
Use e.g. #SBATCH --array=0-7 for eight Slurm workers, with per-worker CPU/memory.
Never run a multi-stage consumer/reducer until this project coverage gate passes.
A thousand-item performance benchmark remains required before claiming scalability.

The coverage gate compares explicit expected and observed IDs, rejects duplicates
and unexpected products, checks readable completion records and input bindings,
validates required output contracts, and distinguishes produced, explicitly empty,
excluded-with-reason, failed, interrupted and missing/pending items. A directory or
scheduler exit code alone is insufficient. The toy helper reports unresolved cases
as issues; use flexlock items/status for detailed failed/pending classification.
Real SAR reducers additionally validate region/date/partition coverage and payload
schema. SST comparison checks matched platform/date membership and model semantics.

A manual coverage check means a deliberate project-owned program, invoked before
reduction, whose report is retained. It does not mean eyeballing a directory count.
If automated after the worker pool, put the checker and reducer in the same
consumer script so a failed check exits before the reducer. afterok only ensures
successful upstream job execution; it does not establish scientific completeness.

## Continue a queue or a model explicitly

An unchanged recorded queue can be drained again after confirming previous workers
have stopped. Done rows are retained; pending rows are processed. Dedup identifies
queue items, not scientific equivalence after code/data changes. Use one controller
per campaign root. Enqueue files do not freeze the importable source environment.

Do not add changed presets to a continuation command. Inspect recorded status,
keep verified products, then launch a new explicit delta queue for chosen repairs
with new record paths. Failed/interrupted rows are not silently retried by replaying
the same queue. Any supported retry operation must preserve earlier failure evidence.
Avoid --force on a whole campaign merely to repair two items.

For model continuation, start a new run pointing to a named checkpoint. Application
code restores weights/optimizer/RNG state and describes continuation semantics.
For stage reuse after a source change, document why the selected preparation remains
acceptable and run only the unfinished/new stage. FlexLock does not judge equivalence.

## Multiple stages in one allocation

The toy cfgmod defines prepare, train and assess under one root. Each writes to a
separate stage directory, with run_lock reads of the earlier stage's record.

```bash
flexlock-run -d examples.slimmer_workflows.cfgmod.cfg -s prepare train assess \
  -o runs_root=/shared/project/runs track=baseline arm=linear run=chain001 \
  --slurm-config slurm/cpu.yaml --print-job-id
```

Stages execute in order within each item. Failure blocks remaining stages of that
item; independent items may continue. This is not a global stage barrier across a
sweep: one item's training can begin while another item's preparation runs.
Use a separate campaign coverage/reduction stage when a global join is needed.
All stages share the allocation and resource profile. Do not put per-stage Slurm
profiles in a multi-select config and expect them to switch allocations.
Do not reuse a stage save_dir across the stages of one item.

## Separate allocations for CPU → GPU → CPU

Use separate single-stage submissions and a short project script. The concrete
producer path and scheduler dependency must name the same producer. Paths are
known at submission; run_lock reads can wait until the consumer starts. Never use
worker-time newest/preset lookup as a substitute for the producer just submitted.

[Small orchestration script](../examples/slimmer_workflows/orchestrate.py) submits
three existing CLI commands, captures IDs using --print-job-id, writes a ledger after
each accepted job and passes --after for the next launch. It requests CPU/GPU/CPU
profiles separately. No checkpoint or upstream record needs to exist when wiring it.

```bash
python -m examples.slimmer_workflows.orchestrate \
  --runs-root /shared/project/runs --track baseline --arm linear --run chain002 \
  --cpu-profile slurm/cpu.yaml --gpu-profile slurm/gpu.yaml --ledger chain002.jsonl
```

This command submits real jobs. Review the config/resource profiles before use.
If training submission fails, preparation remains submitted; the ledger preserves
its ID. Inspect it and launch only the missing stages. Submission is not completion.
Blocked downstream jobs need inspection/cancellation if the producer fails.
For chosen already-complete preparation, omit its launch and dependency, validate
its record/product, and pass its explicit path to training. Do not add old completed
job IDs indefinitely: scheduler dependency lookup has a retention window.

## Slurm configuration and proposed prepare/submit workflow

See the separate [Slurm proposal](slurm_submission_workflow.md). Keep --after and
profiles; support held jobs through Slurm directives today. A future prepare-job
operation would materialize a launch bundle without calling sbatch; its destination
claims and manual-launch bookkeeping must satisfy the core guard contract first.
This proposal adds no pipeline compiler and does not mirror every sbatch flag.

## Review and implementation order

Review these patterns now; implement M1 record/guard contracts and M2 accurate
producer bindings against them. Keep cache/resume policy optional, retain historical
readers and exercise the recipes locally/fake-backend before isolated SAR/SST adoption.
The toy computations exercise plumbing, not scientific acceptance. The draft does
not declare large data identity, simultaneous controllers or prepared submissions
safe before their corresponding acceptance checks exist.
