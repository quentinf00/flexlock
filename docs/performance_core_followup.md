# Performance follow-up: core checks, record files and explicit discovery

2026-10-07. The [benchmark](../reports/2026-10-07-thousand-items-hydra/report.md)
used FlexLock 0.9.0 from the isolated migration checkout at 9ab83a3, including the
preceding guard/discovery/directory/binding changes. It was not an unmodified
published release. df7dfc8 adds benchmark evidence and guidance only. The measured
cost is unacceptable for tiny-item processing; completing the measurement is not
accepting scalability.

## Check placement

Remove redundant work before adding concurrency. Per-item repository fingerprints
and loaded-module path resolution dominate tracked execution. Fingerprint creation
for an optional cache index is currently performed even when smart_run=False;
provenance still needs source identity, but does not intrinsically need a newly
computed cache key and index insertion for each item. Preserve resolved config,
data identity, source evidence and selected upstream references independently.

| Operation | Placement |
|---|---|
| Destination ownership/collision guard | Synchronous, before queue mutation and Slurm submission |
| Verify selected producer and bind effective arguments | Synchronous, before user code |
| Capture source identity | Before execution; share evidence only under a verified frozen-source contract |
| Data hashing / declared output verification | May overlap computation for immutable inputs/outputs, but required evidence/validation must finish before truthful completion |
| Optional index refresh, reports, exports | Can be deferred; do not mutate authoritative provenance after consumers can bind it |
| Repeated source checks within a worker | Reduce shared work while preserving new imports, source changes and symlink behavior; no blind cached-path or mtime-only shortcut |

Asynchronous checks hide latency when substantial computation overlaps them;
they do not remove the filesystem work and may increase contention. Tiny tasks
provide little overlap. Post-completion source/data enrichment is particularly
unsuitable: concrete consumers bind the full materialized producer record digest.
Changing that record later would invalidate the binding. If required checks run
concurrently, completion must wait for them and surface their failures.

The current worker deliberately remains single-threaded during user code for
fork-based scientific workloads. Do not introduce a background worker thread
as the first optimization. Optional off-path work can use controller-side or
separately managed execution without changing the task's provenance contract.
No asynchronous runtime implementation is introduced by this decision note.

## Bookkeeping consolidation

| Current files/state | Candidate simplification | Constraint |
|---|---|---|
| `.flexlock-queue.json` and `.flexlock_marker` | One durable pointer established before dispatch, supporting reservation and record lookup through completion | Preserve queue/task identity, external destinations and ambiguous multi-task destination handling |
| `.flexlock-controller.lock` | Retain a stable mutex inode initially | Atomic metadata replacement cannot silently switch the locked inode; a campaign-root lock alone misses overlapping campaigns with different roots |
| DB snapshot and full per-item `run.lock` | Share campaign source evidence and store per-item deltas; materialized per-item records can remain an export/convenience | Readers must still reconstruct exact provenance and detached artifacts must carry their dependencies |
| DB outcomes plus `results.json`, `run.complete`, `run.error` | Define one authoritative terminal outcome; consider one atomic result/error receipt for standalone runs | Versioned reader migration required; do not silently change result payloads or historical success semantics |
| Fingerprint index and automatic YAML queue dump | Make derived lookup/export work optional or requested | Task membership/status and durable provenance remain core |

Start with the pointer merger and redundant writes, not a wholesale record format
rewrite. The current successful baseline has seven files per item, including
the user's product; pointers and duplicated state are concrete opportunities.
Removing collision protection merely to reduce file count is not an acceptable
optimization. Sharing source evidence reduces serialization but its export/move
contract must remain clear.

## Automatic cache discovery versus manual search

Automatic cache discovery **has not been removed yet**. The caller inventory
and benchmark retained compatibility behavior; Project.submit still defaults
smart_run=True, and legacy scan fallback still defaults on. The agreed slimmer
core direction is to move automatic cross-run reuse out of execution. Fresh
workflow recipes already pass smart_run=False. Runtime removal/default changes
remain implementation and consumer-migration work, not completed work.

A proposed read-only command is:

```sh
# Proposed interface; not implemented yet.
flexlock find -d cfgmod.cfg -s prepare --root /shared/project/runs --match config --format json
```

Reuse the existing config loader, stage selection, overrides and record readers.
Scan explicitly supplied roots once; return candidate paths, completion status,
the chosen comparison scope, and differences/unknowns. A config match is not a
source/data equivalence or scientific acceptance claim. Identity comparisons can
be explicitly requested with their hashing cost made visible. Do not silently
ignore upstream paths or meaningful arguments when normalizing the destination.

The user/agent then selects a concrete candidate, checks its product suitability,
and supplies its path as upstream_run. The search command neither executes,
silently selects the newest match nor rewires a consumer. Existing `flexlock runs`
lists preset membership; it does not implement this configuration comparison.

Migrate explicit SST preparation reuse to selected retained products before
retiring that caller's automatic search. Historical flags/adapters need explicit
deprecation or rejection, not silent ignoring. Optional manual discovery and
comparison survive; automatic reuse is removed from the supported core workflow.

## Hydra month-config reuse

The supplied nextgems sweeps.py registers 720 month nodes, each carrying
yearmonth and correlated 2D/3D catalog tuples. A one-node replacement keeps those
relationships in a resolver:

```python
from hydra.core.config_store import ConfigStore
from omegaconf import OmegaConf

def monthly_catalog(yearmonth, field):
    year = int(str(yearmonth).split('-')[0])
    experiment = ('IFS_9-FESOM_5-production-hist' if year < 2020
                  else 'IFS_9-FESOM_5-production')
    return ['IFS', experiment, field]

OmegaConf.register_new_resolver('monthly_catalog', monthly_catalog)
ConfigStore.instance().store(
    name='base', group='month', package='process_month.pp_fn',
    node=dict(
        yearmonth='???',
        cat_2d='${monthly_catalog:${.yearmonth},2D_hourly_healpix512}',
        cat_3d='${monthly_catalog:${.yearmonth},3D_hourly_healpix512}',
    ),
)
```

Keep existing job/launcher options, select `+month=base`, and sweep the argument
instead of the config group:

```sh
process_month.pp_fn.yearmonth=2019-12,2020-01
```

Generate the full comma-separated month list from the existing generator without
registering its entries. Register the resolver in the configuration module that
workers also import. Override the existing nested yearmonth field directly;
the project's base config currently contains `${..yearmonth}`, so merely adding
a root yearmonth would not necessarily fix its scope.

[Isolated composition proof](../reports/2026-10-07-thousand-items-hydra/month_config_reuse.py)
and [results](../reports/2026-10-07-thousand-items-hydra/month_config_reuse.json)
verify all 720 payloads and four Hydra boundary compositions, including downstream
filename interpolation. No scientific stages, project imports or jobs executed;
the original source was only read. Hydra's [override grammar](https://hydra.cc/docs/1.3/advanced/override_grammar/basic/)
supports sweeping values without selecting a distinct group node per item.

This replacement moves the month/catalog mapping rather than eliminating it.
It also changes discovery: the user's original requirement includes native
`glob(*)` / `glob(20*)` selection of named months. Hydra's glob sweep enumerates
config-group options, not values of an ordinary yearmonth field. With only
month/base registered, a group glob would select base, not discover 720 months.
The proof establishes payload/composition equivalence, not equivalent discovery.
Preserving native group glob requires named month options (which can be small
yearmonth-only aliases to a shared template), or additional config-source/sweeper
plumbing. A manifest plus explicit fnmatch selection and ordinary value overrides
avoids per-month registration but changes the CLI/workflow. The original group
registration is therefore justified by this discovery requirement; the one-node
replacement is not a drop-in solution for the stated usage.
For arbitrary irregular jobs, a frozen manifest indexed by item ID is another
one-config option; it introduces its own loader and provenance responsibility.
Your original registration loop is a reasonable way to represent correlated
choices, and a generic reusable-config benchmark does not prove that your
application becomes simpler. The project's process_month_parallel preset selects
Dask, so the Submitit benchmark is not a measurement of that execution path.

## Implementation order

### Preparation optimization pass — 2026-10-08

Treat automatic cache misses as outside this optimization pass: their default
disablement/deprecation belongs to policy migration. Optimize ordinary cache-off
preparation, measured at 32 seconds for 1,000 items on NFS (36 seconds with source
tracking in a single sample). Keep sweep-file usage and correlated overrides.

The separate 100-item preparation profile took 6.54 seconds. OmegaConf.create
was called 504 times and accounted for 2.39 cumulative seconds; task/config merge
was called 301 times (1.37 seconds); binding transformation took 1.44 seconds.
These overlap. Profiler overhead prevents treating those proportions as an exact
breakdown of the unprofiled 32-second run. Destination guard and reservation calls
took 0.58 seconds combined, and queue insertion/serialization took 0.34 seconds.
Configuration repetition is the first measured target; 2,007 preparation files
remain a separate metadata concern.

Proceed now with a bounded optimization investigation and small implementation
slices, rather than another architecture redesign:

1. Trace controller compilation through Project._submit_sweep and ParallelExecutor.
   The controller already has effective per-item configs. The executor merges
   them again for shared-product-root calculation and destination reservation.
   Identify which master metadata those merges supply before removing them.
2. Reuse validated compiled items/derived destination metadata internally, while
   retaining the existing merge path for low-level executor callers that supply
   actual partial overrides. Do not infer that task_target=None always means a
   complete config. Avoid a new public execution mode or second queue format.
3. Reduce config/container reconstruction during freezing and producer binding.
   A no-binding fast path must preserve latest/run references, indirect relevant
   resolution, literal escaping and argument interpolation. Do not disable the
   guards or blindly mutate caller configs to reduce allocations.
4. Run focused acceptance for interpolation, @ replacements, upstream binding,
   future --after inputs, campaign membership and collision refusal before launch.
   Compare queued effective configs and recorded selections with the baseline.
5. Measure each slice independently: first a 100-item profile and a fresh
   1,000-item mocked submission with cache off, then three repeats once the slice
   is stable. Add a tracked preparation sample, verify pending membership and
   payloads, and record source revision. Do not change source during timed runs.

Keep constructor counts and phase timings in the evidence. Prefer call-site timer
instrumentation for an unprofiled phase breakdown; cProfile is for locating work.
Once configuration reuse is measured and correct, tackle pointer duplication and
the much larger worker source/drift costs separately. Asynchronous execution is
not the first remedy. A drop in constructor counts without a material elapsed-time
improvement is not sufficient acceptance; no speedup or target time is claimed yet.

1. Separate cache-key/index work from required provenance, eliminate repeated
   configuration construction, and optimize loaded-module/source checks while
   retaining the existing correctness cases. Re-run the tracked thousand-item
   case before accepting performance.
2. Consolidate queue/record pointers and authoritative outcome writes with
   historical readers preserved; remeasure metadata work and collision guards.
3. Add explicit manual comparison/search and migrate reuse callers; retire
   automatic discovery from supported execution with a clear compatibility path.

These are implementation priorities, not claims that those changes already exist.
