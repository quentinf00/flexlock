# Bookkeeping inventory: file-saving shortcut rejected

This investigation changes no runtime file format or default. The preparation
files have different responsibilities; fewer files alone does not establish a
safe or worthwhile optimization. Inventory/probe drivers were frozen at **9cb00fc**
with runtime behavior from **866965c**.

## Actual files and responsibilities

The retained plain 1,000-item preparation has **2,007 files** before the benchmark
writes `measurement.json`. Inventory afterward has 2,008. Runtime files under the
campaign root are 2,006; the other measured file is the benchmark Slurm profile.

| File | Prepared count | Responsibility / readers |
|---|---:|---|
| `.flexlock-controller.lock` | 1,001 | Per-product and campaign mutual exclusion; `destination_guard.guard_destinations`; preserved by `save_dir.clean_run_dir` |
| `.flexlock-queue.json` | 1,000 | Product → authoritative queue before workers start; destination guard and selected-producer active-work checks |
| `run.lock.tasks.db` | 1 | Authoritative task membership, lifecycle, results and snapshots; workers, status/query, record materialization, resume and ownership guards |
| Campaign `run.lock` | 1 | Controller source/env/config and shared-product metadata; workers, materializers and source verification |
| `run.lock.tasks` | 1 | Derived terminal-task YAML export; written after submission and when workers finish, not queue authority |
| Pickle / scheduler script | 2 | Materialized worker launch |
| Benchmark Slurm profile | 1 | Input to this benchmark, not per-task bookkeeping |

The locks are empty. The queue pointers total 128,000 bytes in the inventoried
case, versus 786,432 bytes in the database. This is mainly metadata/operation
cost, not large pointer payloads. The initial terminal-task YAML export is only
`[]\n` (three bytes), so deleting it cannot explain a substantial prep speedup.

Successful `task_record="dir"` local execution has seven files per item including
the user's product: mutex, queue pointer, `.flexlock_marker`, `run.lock`,
`results.json`, `run.complete`, and `product.json`. The 100-item inventory has 705
measured files plus the later measurement file. Failed stages additionally use
`run.error`. Shared product roots place task/stage lifecycle files under
`.flexlock-items/<task_id>/<stage_id>` rather than arbitrarily assigning the shared
product directory to one task.

`task_record="db"` already avoids the per-item full `run.lock`. It retains the task
DB, marker, lifecycle/result files and ownership files; it does not remove the
2,000 prepared product mutex/pointer files. DB-only records require retaining the
queue/campaign when moving artifacts.

## Why apparently redundant files cannot simply disappear

**The mutex and pointer are separate mechanisms.** A mutex coordinates live
controllers; a pointer locates pending work after the submitting controller exits.
Locking only the campaign root misses two campaigns with different roots that
target the same products. Atomically replacing a JSON file used as a mutex would
switch its inode while another controller holds the old inode. Merging pointer
content into the mutex would need a different crash-safe update protocol and
coordination with the low-level reservation writer. That is not a small rename.

**The queue pointer and worker marker overlap after execution, but differ before
execution.** The pointer names a queue without claiming that a task/stage receipt
exists. The marker names a specific task ID and is written in its actual receipt
directory. `record.load_record`, `query.run_status`, indexing/reindexing,
`run_record` legacy placeholder handling, overwrite/cleanup, and API resume logic
all depend on this distinction. Precreating today's marker would change occupancy,
query classification and record lookup; a shared root cannot receive one arbitrary
task ID.

**DB status and stage completion are different.** A composite logical task can
fail after an earlier stage has completed. Its earlier `run.complete` supports
stage resuming and output verification despite the logical row being failed.
Removing stage receipts would require a replacement for that fact, not merely a
query of the row's terminal status. Standalone stages also have no task database.
`results.json` is a public return-value artifact and can be a declared output.

**Per-item source evidence is intentional.** Version-2 snapshots retain the
materialized source/env/note actually used by each item, so replacing the campaign
master during a later append does not rewrite historical provenance. Sharing those
fields again would require immutable versioned source evidence, including export
and detached-artifact rules. Inheriting whichever master exists now is unsafe.

## Pointerless nested prototype

For a nested product, the controller ownership guard already searches ancestor
`run.lock.tasks.db` files. An isolated benchmark prototype skips queue pointers for
products under the queue root, retaining pointers for external destinations.
No library implementation was changed and the prototype is not a supported mode.

Three alternating fresh-process pairs, frozen source, one shared NFS host,
1,000 plain items, serial compilation, two metadata I/O workers, cache discovery
off, mocked scheduler:

| Variant | Repeat 1 | Repeat 2 | Repeat 3 | Median | Prepared files |
|---|---:|---:|---:|---:|---:|
| Current | 13.281s | 13.190s | 12.771s | 13.190s | 2,007 |
| Omit nested pointers | 12.381s | 11.425s | 12.729s | 12.381s | 1,007 |

Median improvement is **0.809s / 6.1%**, despite halving file count. All paired
candidate times are lower, but the last difference is only 0.043s. These samples
do not justify treating the gain as a universal constant or comparing directly
against earlier benchmark host conditions. Six queues / 6,000 configs are
equivalent after normalizing only output-case prefixes. Each has 1,001 stable
mutex paths, one mocked scheduler call and no scientific products.

### Counterexample: selected producer can bind stale provenance

`has_active_destination` currently checks the selected directory's own DB and its
queue pointer. It deliberately does not search ancestors. The controller guard
does search ancestors. A synthetic fixture with an existing old producer lock,
a nested pending replacement queue and no pointer proves:

1. The controller guard refuses another launch because the ancestor queue is active.
2. The producer active-work reader returns false.
3. Submit-time `run_lock` binding reads and records the **old artifact**.

This is also a blind spot for pointerless historical ancestor queues; dropping
new nested pointers would make it normal. The counterexample is retained, not
accepted. Runtime pointers remain in place. Config equality alone does not validate
reservation or provenance behavior. Stage-start digest checks do not replace this
guard: the old lock may remain unchanged while replacement work is queued.

## Recommended migration order

1. **Consolidate readers first, preserving current writers.** Introduce one private
   queue-reference parser/locator used by ownership and upstream binding. Retain
   both pointer/marker formats and relative marker DB semantics. Detect ancestor
   queues for selected producers too; reject unreadable reservations rather than
   treating them as absent. Keep this separate from automatic cache search.
   Verify pending/running replacements, future producers with `after`, terminal
   queues, external destinations, nested/legacy queues, multiple queues and shared
   roots. Measure large upstream cohorts: ancestor probes and active-row decoding
   can otherwise erase the small write saving. Do not add a global stale cache.
2. **Specify a versioned unified descriptor independently of the mutex.** It names
   the queue from reservation onward and gains a task/stage reference only in the
   corresponding receipt directory. Reservation alone must not mean completion or
   silently select one item at a shared root. Preserve relocation semantics for
   relative marker paths and self-contained `task_record="dir"` exports. Read new
   and old formats before changing writers; old readers cannot be assumed safe.
3. **After reader adoption, merge pointer and marker writes.** One atomic descriptor
   can replace the two logical pointers in completed task directories. This saves
   one file per ordinary completed task, but **does not halve prepared files**:
   the current marker is not present at preparation. Keep mutex inodes separate.
4. **Reconsider omitting nested descriptors only if worthwhile after reader timing.**
   External products still need a locator. Avoid expanding a tiny file saving into
   a new registry/selection framework. Make YAML exports and optional index work
   explicit later, with compatible replacements for current readers.

This is a concrete reader-first migration plan, not a default format change or
production rollout. It preserves FlexLock's thin role: accurate concrete artifact
references, provenance and mechanical ownership guards. Workflow guidelines still
own choosing artifacts, coverage checks and decisions about rerunning stages.

Evidence: [inventory and counterexample](inventory.json), [probe](probe.py),
[manifest](manifest.json), [summary](summary.json), [validation](validation.json),
[case driver](case.py), [matrix driver](matrix.py), [analysis](analyze.py).
The driver requires `PYTHONPATH` to select this validation checkout; an initial
probe without it imported the installed package and failed before running.
Raw comparison artifacts:
`/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-09-bookkeeping-inventory`.
