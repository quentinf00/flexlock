# Workflow guidelines

These guidelines describe FlexLock 0.10. Use the [migration notes](release_0_10.md)
when upgrading older callers. Runnable examples are maintained in
[the example directory](https://github.com/quentinf00/flexlock/tree/v0.10.0/examples/slimmer_workflows).
Track/arm/run is optional: processing products need not be experiment arms.

## Transition toward fresh pipeline baselines

FlexLock does not provide scientific-producer legacy adapters. During the pre-1.0
transition, a project can consume historical products with explicitly incomplete
provenance, keeping any adaptation in project code. Track current input identity
and describe the gaps; do not invent historical upstream evidence.

After API/workflow stabilization, prefer a fresh whole-pipeline execution using the
agreed release and current bookkeeping. That new chain should become the baseline
for future processing and experiments after coverage and scientific validation.
Existing retained-product examples are useful transition checks, not a requirement
to support old project conventions indefinitely. See the
[fresh-baseline handoff](project_adoption_handoff.md#fresh-baselines-after-api-stabilization).
Compute scope and timing belong to each project; these guidelines launch no reruns.

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
An arm label does not automatically select a model or loss: the arm config must
apply that choice explicitly, for example by importing its model node. The toy
config's arm is a path label, not a hidden variant switch.
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
            data=dict(dataset='${...input_path}')),
        _outputs_=dict(model=dict(path='model.pt', sha256=True))),
)
```

Put the concrete producer in one root anchor and read related facts from its record.
Avoid duplicating dataset path, normalization and model settings in every consumer.
A small project helper can expose a dataset/checkpoint binding when several values
belong together. The executable [acceptance helper](../examples/slimmer_workflows/bindings.py)
requires a named completed record and declared output integrity. A standalone
producer needs a done queue row; a composite producer needs the selected stage
record and its completion evidence, since later stages can still be running. Train/assess call it at consumer start. run_lock remains a reader and can
read failed records; using those records as accepted products is a separate decision.
The helper returns plain paths and never searches for a replacement. Real projects
also validate grid/mask/model schema and compatibility.
Facts describing a checkpoint should be validated against the checkpoint contents.
A record is not proof of compatibility between grids, masks or model architectures.

The resolver is run_lock; recorded callable arguments are below config. Track the
effective argument with data=dict(dataset='${...input_path}'), so an input_path
override also updates data tracking. The relative reference survives stage selection
and renaming. Avoid repeating its original run_lock expression in tracking config.

Project.get returns a detached config. After choosing a retained producer or receiving
an actual result path, update the root anchor in proj.defaults before selecting the
consumer. Assigning cfg.save_dir on an already selected stage does not update other
stages' root references. Existing cross-stage save_dir configs need an explicit root
update too. See the [caller inventory and migration examples](optional_policy_inventory.md).


Direct run_lock reads now automatically record the canonical producer, requested
field, returned value/default usage and producer-record SHA256, and add lineage from
the same read. Repeated fields from one producer use one coherent read during stage
resolution. A missing producer with an explicit fallback is recorded as a fallback;
it does not manufacture producer lineage. Manual prevs remain useful for independent
dependencies that cannot be derived from arguments, but remove redundant/stale ones.

Keep lightweight automatic discovery. _snapshot_.discover accepts repos and prevs
boolean flags, both defaulting to True. Repository discovery follows the callable's
configured _target_ nodes, including nested ones, when their modules resolve to
Git checkouts (including editable/src installs). Ordinary imports inside callables
still need explicit declarations. Auto-discovered scopes contain the target source
files; include helper files explicitly when required. Capture and cache comparison
use the same per-repository include/exclude scope, applied before Git staging.
An explicit repository entry without include captures the full non-ignored checkout;
an explicit include can select a broader package subtree. An explicit entry for a canonical checkout prevents a second unfiltered
alias. Explicit declarations cover extra repositories/scopes. No discovered repository
means absent evidence and a visible warning, not proof that imports were captured.
Disable discovery explicitly for deliberate untracked targets.

For ordinary projects, reuse a broad explicit scope such as src/, configs/ and
scripts/ across stages. Introduce stage-specific includes only for a concrete need.
The [source-attribution contract](source_attribution.md) preserves shared
campaign capture in repos and exposes each invocation's effective source_scope in
records/readers. These are output metadata fields; _snapshot_.repos syntax is unchanged.

Data-ancestor discovery only examines declared data paths and labels its evidence
as data_ancestor in the record's discovery section. Containment is an inferred
association, not output ownership or scientific acceptance. discover.prevs=False
disables that heuristic, not known direct run_lock references or explicit prevs.
Unambiguous declared-output association is a future improvement; no global record
scan, newest-run substitution or artifact-selection policy is introduced here.

Existing concrete run_lock producers bind before queued dispatch. The worker checks
their full materialized record digest before calling user code; replacement, deletion
or any record change fails the task. --force on the consumer does not waive this check.
Keep selected producer records stable, or choose a fresh path and resubmit after review.
Missing concrete promised producers paired with --after, or earlier stages in an ordered
pipeline, resolve at consumer start. A readable existing record with a missing required
field fails before submission. Explicit defaults bind now, including null. latest
selection freezes at dispatch; --enqueue merely exports config and is not dispatch.
Unpinned run references under --after are rejected before dispatch. Use an explicit
pin resolved at submit, or a concrete future producer path with run_lock. Pending/running queue reservations
identify promised producers even when their controller placeholder run.lock exists.
Pair them with --after; completion is checked by project acceptance code. Directory
identity rereads selected relative paths and bytes; single-file metadata caching
remains a labelled compatibility policy. Keep inputs stable while being read.

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
@ node replacement remains useful for model/data variants. For a project stage
that accepts a model config, expose the alternatives as module attributes:

```python
# myproject/configs/runs/seed3.py
from myproject.configs.models import small, wide
# cfg['train'] uses small by default; wide remains available to @ lookup.
```

```bash
flexlock-run -d myproject.configs.runs.seed3.cfg -s train \
  -o arm=wide run=seed3-wide -O model=@wide
```

The selected concrete upstream should remain visible in the run config. See
[CLI scope](cli_reference.md).

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
Fresh submission performs no automatic cache lookup. Do not pass the retired
smart_run/search_dirs keywords, including smart_run=False. Select retained producers
explicitly and use fresh destinations for new work.
The thousand-item measurements (internal validation evidence)
show why this matters for fresh file-list campaigns: legacy fallback can repeat
a directory traversal for each cache miss. Claim batching can reduce queue
overhead, but choose it against task duration, load balancing and recovery needs.
Source tracking also has a substantial per-item cost in the current implementation;
keep its scope explicit and retain evidence when deciding what to reuse.

Choose a fresh directory by default. --force is intentional in-place re-execution,
not ordinary pipeline continuation. The isolated controller now checks all destinations
before invalidating markers or dispatching. Pending/running queue rows reserve paths;
force cannot seize them, including held jobs. Force replaces current records and keeps
products for in-place rewriting; it does not archive old evidence. Use a fresh run or
copy evidence first when downstream historical references need to remain valid. An immutable code checkout/environment avoids source
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

Generate the listing once, then retain it rather than rerun glob at each stage:

```python
import hashlib, json
from pathlib import Path

paths = sorted(Path('/shared/input').glob('*.json'))
rows = [dict(item_id=f'file{i:06d}', input_path=str(path.resolve()),
             sha256=hashlib.sha256(path.read_bytes()).hexdigest(), disposition='process')
        for i, path in enumerate(paths)]
with open('manifests/files-v1.json', 'x') as stream:
    json.dump(rows, stream, indent=2)
```

This small-file example reads the inputs to hash them. A domain-specific immutable
manifest can avoid repeated scans of huge inputs. IDs assigned from an enumeration
are stable only within this frozen listing; a delta listing must retain existing IDs
and allocate new ones, or use project IDs/content-based identifiers. Make exclusions
explicit before exporting the queue, instead of dropping files without a trace.

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
Queue entries carry the frozen input SHA256. Processing hashes and parses the same
bytes and refuses a changed input. Coverage checks the recorded expectation and
product's input identity against the manifest. It does not substitute today's file
for historical evidence. Add --check-current-inputs to check current bytes separately.
Real SAR reducers additionally validate region/date/partition coverage and payload
schema. SST comparison checks matched platform/date membership and model semantics.

A manual coverage check means a deliberate project-owned program, invoked before
reduction, whose report is retained. It does not mean eyeballing a directory count.
If automated after the worker pool, put the checker and reducer in the same
consumer script so a failed check exits before the reducer. afterok only ensures
successful upstream job execution; it does not establish scientific completeness.

### Several files per queue task

A chunked task can write one declared, hashed `outcomes.json` containing a row per
input member. Freeze chunk-to-member assignments and concrete producer paths before
submission; reduction must check that frozen membership, not just enumerate the
chunks that finished. NextGEMS storm preprocessing uses this pattern. Its month
sweeps belong to the separate nextgems_tc_tracking project.

```python
frozen_chunks = [dict(chunk_id='chunk001',
    producer_record='/shared/runs/storms/campaign001/chunk001',
    items=['storm001', 'storm002'])]
# Producer config: chunk_id='chunk001', outcomes_path='.../outcomes.json',
# _outputs_=dict(outcomes=dict(path='outcomes.json', sha256=True))
# outcomes.json:
# {"chunk_id":"chunk001", "items":[
#   {"item_id":"storm001", "outcome":"ok"},
#   {"item_id":"storm002", "outcome":"missing_zarr"}]}
from examples.slimmer_workflows.chunk_coverage import check_chunk_coverage

report = check_chunk_coverage(frozen_chunks)  # missing_zarr blocks by default
if report['issues']:
    raise RuntimeError(report['issues'])  # retain this report; do not aggregate
```

Only after a project decision can a caller pass
`accepted_outcomes=['missing_zarr']`. The report retains named accepted non-OK
members; they do not become OK products. Missing/duplicate/unexpected member rows,
unfinished chunks and changed output manifests block acceptance. The example
checks manifest integrity and accounting, not the contents of each scientific
product: add the project's schema, existence and byte-identity checks as needed.
It does not reconstruct missing historical input/source evidence.

The single-item directory checker skips exactly the internal `.flexlock` directory;
other unexpected directories still count as issues. Prefer shared record readers
over inferring task outcomes from the directory layout.

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

## Frozen reassessment

Select both preparation and training records explicitly and give assessment a fresh
run label. In the toy configuration:

```bash
flexlock-run -d examples.slimmer_workflows.cfgmod.cfg -s assess \
  -o upstream_run=/shared/runs/baseline/linear/chosen/prepare \
     training_run=/shared/runs/baseline/linear/chosen/train \
     runs_root=/shared/reassessments run=protocol-v2
```

For SAR, bind the chosen preparation/dataset record and document its continued
suitability. For SST, bind the checkpoint/training config and prepared data, then
validate legacy/native inference conventions and the matched comparison cohort.
No preparation or training is relaunched by selecting only assessment. Retain the
protocol/cohort manifest and its coverage report with the new assessment record.

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
its ID. This small example ledger is best-effort: a crash after acceptance but before
writing the ID leaves an ambiguous launch. Inspect the scheduler before retrying; a
missing ledger entry does not prove no job was accepted. Launch only verified missing
stages. Submission is not completion.
Blocked downstream jobs need inspection/cancellation if the producer fails.
For chosen already-complete preparation, omit its launch and dependency, validate
its record/product, and pass its explicit path to training. Do not add old completed
job IDs indefinitely: scheduler dependency lookup has a retention window.

## Slurm configuration and proposed prepare/submit workflow

See the separate [Slurm proposal](slurm_submission_workflow.md). Keep --after and
profiles; support held jobs through Slurm directives today. Next extract a backend
materialization seam returning a real payload, script and submission argv. Defer a
public managed prepared-launch lifecycle. Raw manual export is advanced project use
with explicit limits; no new pipeline compiler or sbatch option catalogue is needed.

## Review and implementation order

Review these patterns now; finish M1 directory identity and M2 accurate producer
bindings against them. The isolated controller/queue guard is implemented and tested;
its limits are explicit in the Slurm workflow. Keep cache/resume policy optional, retain historical
readers and exercise the recipes locally/fake-backend before isolated SAR/SST adoption.
The toy computations exercise plumbing, not scientific acceptance. The draft does
not establish large data identity or prepared-submission safety. Controller collision
checks cover the supported Project paths; advanced queue mutation requires one controller.


## Validated transition examples (2026-10-14)

See the project transition draft (internal validation evidence) and acceptance report (internal validation evidence). The SST retained-matchup reassessment and SAR legacy split were executed with installed 0.9.2; neural-field config resolution was checked without training.

Start with one config entrypoint, explicit retained-artifact bindings, and a fresh absolute run root. Add stage or track modules only when actual reuse warrants them. Keep historical receipts and artifacts in place. A historical config.save_dir can be relative: resolve against its original project context or use the selected producer directory explicitly, rather than the new consumer working directory.

Data snapshots should reference the effective stage argument, so overrides update both execution and evidence. Likewise, explicit prevs should follow the argument that selects the producer. Changing an input independently of its producer binding needs a deliberate lineage review.

For SAR-style file processing, freeze membership before scheduling and give each item its own receipt directory. Bind frozen SAFE membership to exact queue tasks and CSV paths, then check accepted cohort coverage before dataset assembly. For the current SAR extractor, successful task status plus an absent CSV establishes an empty extraction if products were not moved/deleted. Missing CSV alone does not. Failed or unfinished tasks block assembly; existing CSV reuse requires deliberate provenance checks. Mandatory outcome receipts are not required. The current SAR assembler silently skips missing CSVs and needs this workflow gate before adoption.

For separate Slurm resources, keep the small orchestration script and --after dependencies. Capture accepted job IDs and persist them immediately; a frontend reporting failure after submission must not trigger automatic resubmission. The --print-job-id CLI output is a submission receipt, not a completed execution result.

SAR adoption prerequisite: the enhanced extractor's `iter_safe_ds` and `safe_feats`
currently catch read/feature exceptions and continue. Successful status therefore
cannot yet certify legitimate emptiness or complete processing. Propagate errors,
or explicitly account for partial errors, before applying the status/presence rule
to actual extraction. Mandatory outcome receipts do not repair suppressed errors.
