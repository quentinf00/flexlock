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

Start with compatible reader consolidation before changing pointer writers, not a
wholesale record format rewrite. The current successful baseline has seven files per item, including
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
improvement is not sufficient acceptance.

The [first preparation slice](../reports/2026-10-08-preparation-reuse/report.md)
is implemented at 0629889. Effective executor configs are reused across the
shared-output and destination guard passes, while partial overrides still inherit
master defaults. Fresh cache-off 1,000-item medians fell from 30.807s to 23.315s
(24.3%, three repeats per revision). The 100-item profile shows 201 merges and
404 OmegaConf creations, down from 301 and 504. Peak RSS increased about 7.1 MiB;
file count remains 2,007. All six queues have equivalent item payloads after
normalizing destination prefixes; 100 local products match input checksums.
Focused acceptance covers 183 distinct cases across the initial run and rechecks,
with initial failures and baseline reproductions retained. Source-tracked
preparation took 31.500s in one sample; tracked worker costs remain unoptimized.
The next slice is safe freezing/binding reconstruction reuse. Preparation is still
too slow; no target time or production scalability is accepted.

That [second slice](../reports/2026-10-08-freeze-binding-reuse/report.md) is now
implemented at a32d227. The sweep compiler reuses freezing's detached config for
binding and skips binding only after full freezing leaves no interpolation syntax.
Producer/custom-resolver reads still use the complete guarded binding path.
Fresh 1,000-item medians fell from 23.315s to 20.209s (13.3%, three repeats;
ranges overlap), or 34.4% below today's original 30.807s baseline. Per 100 items,
OmegaConf creations fell from 404 to 204; merges remain 201. Final focused suite:
198 passes; six equivalent queues; 100 independently verified local products.
Source-tracked preparation took 23.175s in one sample; file count stays 2,007.
Next inspect repeated queue-row reading/materialization and nonblocking result
collection, with phase timings and preserved tag/resume/record semantics. A new
fixture exposed an existing escaped-literal limitation in the old two-pass path;
that separate fix needs a compatibility regression before broad adoption.

The [queue-reader slice](../reports/2026-10-08-queue-record-selection/report.md)
at 6211ef6 selects terminal/requested rows before decoding, reuses result hashes,
and uses optional safe LibYAML parsing with the existing timestamp semantics and
Python fallback. Final focused acceptance: 155 passes, equivalent queues and 100
verified local products. Record materialization drops to 0.068 cumulative seconds
per 100-item profile, but the 1,000-item median is 19.948s versus 20.209s: **no
meaningful additional elapsed-time speedup is established**. Files remain 2,007.
An unprofiled diagnostic sample (14.617s total) measured 6.4s merging/freezing,
4.8s guard entry/exit plus reservation writes, and 0.25s record materialization.
Nested timers overlap; this single faster run is not the accepted timing result.
Next deduplicate repeated ancestor probes within destination preflight, preserving
per-product locks and legacy/current ownership checks; measure with matched fresh
comparisons and phase timers before accepting further speed claims.

The [bounded I/O pass](../reports/2026-10-08-preparation-io/report.md) is implemented
at a27a304. Unique ancestor probes are deduplicated; product metadata reads and
reservation writes use two joined I/O workers under held controller locks.
Config resolution, lock acquisition and SQLite commits remain coordinated. An
interleaved original/1/2/4 comparison measured medians 16.120/17.724/15.249/15.223s.
Two workers were faster than the original in each corresponding repeat; four's
median was essentially identical with more variation. Reservation median fell
2.661s → 1.509s. Deduplication alone did not establish a speedup; files stay 2,007.
Default acceptance: 120 passes, two expected serial join-test skips, 12 equivalent
queues and 100 verified products. Required failures join all I/O before releasing
locks and prevent dispatch. Next investigate configuration reuse/batched process
compilation with resolver/import/lineage semantics and startup costs explicit;
these preparation threads do not make current resolver registration thread-safe.

The [configuration-process investigation](../reports/2026-10-08-config-processes/report.md)
confirms that isolated spawned processes can compile batches of canonical configs
with equivalent captured producer records. Three-repeat 1,000-item compilation
medians: plain 4.246/3.040/1.790s and producer-bearing 11.043/6.416/3.734s for
serial/2/4. Startup and result transfer are included; executor/queue/guard work is
excluded. Four-process producer binding has a retained 45.140s outlier. A 100-item
plain smoke is slower with processes (0.490s serial versus 0.773/0.752s).
Parent-only custom resolver registration fails under spawn; explicit initializer
registration reproduces it. Temporary global resolver replacement and the global
preset lineage stack constrain threads; run-lock capture itself is context-local.
Runtime defaults are unchanged by this prototype. Next define an eligible config
subset/context reproduction, retain serial fallback, investigate the outlier and
run full-submission acceptance before enabling process compilation. Continue
avoiding redundant reconstruction; a new general pipeline framework is unnecessary.

The [full process-preparation experiment](../reports/2026-10-08-process-preparation/report.md)
at fd4428c integrates a private opt-in compiler with pickled OmegaConf transport,
canonical-config eligibility and serial fallback. Default adoption is rejected.
Full 1,000-item medians for serial/2/4 processes: plain 19.413/22.406/16.842s,
producer-bearing 28.393/24.363/94.644s. Four-process producer compilation stalls
up to 163.680s with only 14.186 aggregate child CPU seconds; plain compilation
also stalls. Waiting is evident, its source remains unproven. Focused acceptance:
165 passes, two expected skips, 18 equivalent queues, 612 independently verified
products (512 actually process-compiled). Interactive contexts also stay serial.
Files remain 2,007. Preserve serial defaults; next reduce the executor's repeated
merge/reconstruction of already-compiled items while retaining public partial
overrides. Per-worker timing diagnostics are needed before reconsidering pools.

The [compiled-item guard reuse](../reports/2026-10-08-compiled-guard-reuse/report.md)
at 1244e70 removes the executor's second merge for Project's frozen configs under
its minimal wrapper, retaining low-level/default/historical-row merges. Serial
compilation stays default. Alternating 1,000-item pairs improve plain median
17.031 → 14.128s (17.0%) and producer-bearing 26.560 → 23.447s (11.7%); every
corresponding large pair improves. Executor merges fall 1,000 → zero. Peak RSS
falls about 30/45MiB. Small single-pair timing does not demonstrate a speedup.
161 distinct focused passes, two expected skips; 16 equivalent queues / 14,200
configs, 100 verified local products, matching source trees/env with generated
shadow commit IDs retained. Files remain 2,007. Next inventory pointer/marker
bookkeeping and remaining preparation phases before further optimization, retaining
durable lock inodes, ownership and historical readers; tracked-worker source costs
and automatic discovery migration remain separate.

The [bookkeeping inventory](../reports/2026-10-09-bookkeeping-inventory/report.md)
finds 1,001 mutexes plus 1,000 queue pointers in the 2,007-file prepared fixture.
A retained prototype omitting nested pointers halves file count but improves the
matched median only 13.190 → 12.381s (6.1%). Default adoption is rejected: a
counterexample binds an old producer while ancestor replacement work is pending,
because upstream ownership detection lacks the controller guard's ancestor lookup.
No runtime format changes. Next consolidate private queue-reference readers and
fix that ownership gap while preserving current writers, then measure upstream
cohort costs before versioned pointer/marker migration. A pointer/marker merger
saves a completed-item file, not a prepared-item file; stage completion and
immutable item source evidence cannot be discarded as duplicates.

The [shared queue readers and ancestor guard](../reports/2026-10-09-queue-reference-readers/report.md)
at 8ad211c fix required producer binding against active ancestor replacement work,
including stale terminal pointers. Current/legacy marker readers share a private
implementation; writers and 2,007 prepared files remain unchanged. Acceptance:
166 focused passes, two expected skips, plus 72 overlapping legacy rechecks;
six equivalent prepared queues, 6,000 completed and 600 future bindings. Matched
medians: preparation 13.373/13.289s, 1,000 completed bindings 10.161/10.626s,
100 future bindings from 1,000 pending rows 12.863/13.299s. No preparation speed
gain is established. Next profile repeated active-row decoding/path scans before
writer migration, preserving mutable ownership and historical destination fallbacks.
The reader fix does not establish compatibility with older installed readers.

1. Separate cache-key/index work from required provenance, eliminate repeated
   configuration construction, and optimize loaded-module/source checks while
   retaining the existing correctness cases. Re-run the tracked thousand-item
   case before accepting performance.
2. Consolidate queue/record pointers and authoritative outcome writes with
   historical readers preserved; remeasure metadata work and collision guards.
3. Add explicit manual comparison/search and migrate reuse callers; retire
   automatic discovery from supported execution with a clear compatibility path.

These are implementation priorities, not claims that those changes already exist.
