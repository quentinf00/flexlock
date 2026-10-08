# Configuration compilation and resolver state — 2026-10-08

**Configuration compilation can be parallelized with isolated processes.** The
current thread restriction comes from FlexLock temporarily replacing OmegaConf's
process-wide resolver registrations, plus a global preset-lineage recorder stack.
OmegaConf remains a substantial CPU cost, alongside filesystem bookkeeping. This
investigation adds a retained prototype and evidence; it changes no runtime API or
execution defaults.

## What resolvers do

`${input_root}/${item}.bin` contains ordinary references to config values. A colon
expression such as `${run_lock:${upstream_run},config.output_path}` calls a named
function registered with OmegaConf. The current built-ins are:

| Resolver | Meaning |
|---|---|
| `run_lock` | Read a selected upstream record field, preserving its native type; capture the producer identity and reads for provenance |
| `latest` | Select the filesystem path with the newest modification time among glob matches |
| `run` | Select a completed run of a preset, optionally pinned; record its lineage |
| `now` | Format the current time; deprecated in favor of explicit save-directory policy |
| `vinc` | Compute the next versioned path; deprecated in favor of atomic save-directory policy |

Users can register their own functions too. These functions may read mutable
filesystem/environment state or run arbitrary Python, so config compilation is
not necessarily a pure dictionary transformation.

For the upstream pattern, freezing resolves the arguments first:

```text
${run_lock:${upstream_run},config.output_path}
→ ${run_lock:/chosen/run/A,config.output_path}
```

FlexLock temporarily substitutes a resolver that returns the call string instead
of reading A. This keeps a promised input live until binding/stage start. The
binding pass then reads concrete existing A, captures the selected field and full
record digest, and serializes both. A required future producer remains deferred
only through the supported future/dependency path. `latest` selection is evaluated
in the existing submit-time binding pass; it does not silently reselect later.

## Why current compilation threads race

OmegaConf stores registered resolver wrappers in `BaseContainer._resolvers`, a
class-level registry in the installed OmegaConf 2.3.1. FlexLock `_stubbed`,
`defer_unpinned_runs` and concrete binding temporarily replace entries in that
registry and restore them afterwards. These substitutions affect every config in
the process, not just the config being frozen.

A controlled two-thread experiment installed the freeze stub in one thread and
resolved a producer reference in the other. The other config received the frozen
call string; after the context exited it received the actual value, 99. This
[visibility reproduction](thread-registry-visibility.json) demonstrates the shared
state directly. Overlapping replacements/restorations would also make phase timing
and read capture unreliable.

Preset `${run:}` lineage uses a global `_recorders` list with append/pop contexts,
another thread constraint. Existing `run_lock` capture uses a `ContextVar`, so
that particular capture object already has context-local state. Do not treat all
provenance state as uniformly global.

Global registration is not an unavoidable reason to retain temporary mutation:
a permanent resolver dispatcher with context-local phase state could replace the
swaps, and the preset stack could become context-local. That redesign would need
compatibility checks. It would not by itself establish CPU speedup from threads
on this CPython 3.11 build; the current merge/freezing work is largely Python.

## Spawned-process prototype

The [driver](process_compile.py) compiles batches of 50 items using the existing
merge → freeze run refs → validate future paths → freeze/bind functions. Each
spawned process imports FlexLock and gets its own resolver registry. The parent
sends a plain base config once per worker and batches of item IDs, then receives
plain compiled configs with captured provenance. The prototype performs no
scientific execution, queue insertion, destination reservation or scheduler call.

Timing includes pool startup/imports, initialization, compilation, result transfer
and pool shutdown. Equivalence/digest checks follow the timer. For each fixture,
all results have the same full serialized payload digest across worker counts and
repeats. The source stayed fixed at **914fbb3** throughout measurement, host
`compute-118-39`, 16 CPUs in the measured affinity mask. This demonstrates a
prototype with CPU headroom; a controller allocation may have fewer CPUs.

| 1,000-item compilation, three-repeat median | Serial | 2 processes | 4 processes |
|---|---:|---:|---:|
| Plain self-contained file-list config | 4.246s | 3.040s | 1.790s |
| Config reading one existing producer | 11.043s | 6.416s | 3.734s |

Orders rotate across repeats. Four-process plain compilation improved by about
58%; two-process producer compilation improved by about 42%. These are compilation
figures, not full submission medians, and do not include the second executor merge
pass. They cannot be subtracted mechanically from earlier whole-preparation runs.

The four-process producer repeats were **3.734s, 3.645s and 45.140s**. The severe
outlier is retained; its cause is unresolved. Two processes were more stable in
this bounded experiment. Producer fixture values include nested native types and
literal interpolation text; each compiled item captures the exact producer record.
All 9,000 producer-bearing results across the large cases retain one captured
producer read per item. A later synthetic producer replacement is rejected by normal stage-start
verification of an equivalent bound config.

A single 100-item smoke comparison shows the startup boundary:

| 100-item compilation, one sample | Serial | 2 processes | 4 requested |
|---|---:|---:|---:|
| Plain config | 0.490s | 0.773s | 0.752s |
| Producer-bearing config | 1.217s | 1.104s | 1.071s |

With batch size 50, only two batches exist for 100 items; four requested workers
do not imply four useful concurrent workers. Small plain sweeps were slower with
processes. No universal batch size or automatic threshold is established.

## Resolver/context compatibility

A parent-only custom `offset` resolver fails in spawned children with
`UnsupportedInterpolationType`. Explicit registration in the worker initializer
restores equivalent output. This is the central missing contract for transparent
process compilation: importing FlexLock recreates its built-ins, not arbitrary
user registry entries, closures, caches or side effects.

Additional assertions confirm that explicit future producer paths remain exactly
deferred and that equivalent captured bindings reject a later producer replacement.
Coverage does not establish generic compatibility for preset selection, `@` swaps,
structured-config validation/cache metadata, dynamically imported config modules,
interactive execution, arbitrary custom resolvers or complete submission flows.
Plain-container transport drops config metadata; an integrated path must preserve
its semantics or restrict eligibility explicitly.

## Recommendation

Keep OmegaConf for configuration semantics. Continue eliminating redundant
construction where ownership/default inheritance can be proven. Process batching
is a viable candidate for large, eligible sweeps, with a serial path for small or
unsupported configurations. Before integrating it, define how user resolver
registration and config context are reproduced, honor the controller CPU budget,
measure small/large sweeps end to end, and retain the existing producer/collision
acceptance cases. Do not enable a generic process path based solely on these two
synthetic config fixtures or add a general workflow framework to handle this.

Filesystem metadata I/O means directory creation, stat/existence checks,
lock/pointer opens, pointer reads, writes/renames and lock release—the work around
the 2,007 bookkeeping files. SQLite insertion/serialization is measured separately
(the earlier wall-clock diagnostic measured 1.3s for queue work and 4.8s for guard/
reservation work). Independent I/O already has two joined workers. Required
checks/commits still finish before scheduler dispatch regardless of CPU concurrency.

Evidence: [large cases](large-results.json), [small smoke](small-results.json),
[summary](summary.json), [commands](commands.json), [source/runtime](source-evidence.json),
[thread visibility](thread-registry-visibility.json). Raw fixtures/evidence remain
under `/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-config-processes*`.
The driver intentionally replaces a synthetic producer to check binding integrity;
it does not modify scientific inputs or consumer installations.
