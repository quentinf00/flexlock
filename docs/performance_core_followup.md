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
For arbitrary irregular jobs, a frozen manifest indexed by item ID is another
one-config option; it introduces its own loader and provenance responsibility.
Your original registration loop is a reasonable way to represent correlated
choices, and a generic reusable-config benchmark does not prove that your
application becomes simpler. The project's process_month_parallel preset selects
Dask, so the Submitit benchmark is not a measurement of that execution path.

## Implementation order

1. Separate cache-key/index work from required provenance, eliminate repeated
   configuration construction, and optimize loaded-module/source checks while
   retaining the existing correctness cases. Re-run the tracked thousand-item
   case before accepting performance.
2. Consolidate queue/record pointers and authoritative outcome writes with
   historical readers preserved; remeasure metadata work and collision guards.
3. Add explicit manual comparison/search and migrate reuse callers; retire
   automatic discovery from supported execution with a clear compatibility path.

These are implementation priorities, not claims that those changes already exist.
