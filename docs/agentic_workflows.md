# Agentic Workflows

FlexLock already persists everything needed to reconstruct experiment history
(`run.lock`, shadow git commits, data hashes, lineage, the fingerprint index, the
task DB, and tags as git refs). This page documents the **machine-readable query
commands** that turn that on-disk state into a stable, agent-facing contract, the
**shipped skills** that encode common workflows, and the **static HTML report**.

All query commands are side-effect free: they read `run.lock` with
`yaml.safe_load` (never resolving interpolations, so no resolver fires and no
directory is created).

## The contract commands

| Command | Purpose | Machine format |
|---|---|---|
| `flexlock show <run>` | one run's status/metadata/lineage/config | `--format json` |
| `flexlock graph <root>` | the whole experiment DAG | `--format json` (also `mermaid`/`dot`) |
| `flexlock why <a> <b>` | explain a difference (config/data/git + commits) | `--format json` |
| `flexlock stages -d <defaults>` | list runnable stages, unresolved | `--format json`/`keys` |
| `flexlock-diff … --format json` | compare two snapshots | `{match, diffs}`, exit 0/1/2 |
| `flexlock report <root>` | self-contained HTML report | — |

Every JSON payload is gated by a `schema_version` (currently `1`).

### `flexlock show --format json`

```json
{"schema_version":1, "path":"/abs", "kind":"run|sweep_master|sweep_task",
 "status":"complete|failed|interrupted|running|pending|unknown", "status_detail":null,
 "timestamp":"...", "note":null, "target":"myproject.train.train",
 "fingerprint":null, "tag":null,
 "error":{"exc_type":"...","exc_message":"...","traceback":"...","timestamp":"..."},
 "config":{...}, "results":{...},
 "repos":{"main":{"commit":"...","tree":"...","path":"..."}},
 "data":{"train":"xxh64..."},
 "tasks":{"pending":0,"running":0,"done":8,"failed":2,"interrupted":0},
 "lineage":{"upstream":[{"name":"extract","path":"/abs","timestamp":"..."}],
            "downstream":[{"path":"/abs","timestamp":"...","note":null}]}}
```

`status` precedence: a `.flexlock_marker` (sweep task) is classified from its task
DB row; otherwise `run.complete` → `complete`, `run.error` → `failed`, `run.lock`
+ task DB → `sweep_master` (aggregated `tasks` counts), bare `run.lock` →
`interrupted` (no liveness probe — it may still be running), else `unknown`.

### `flexlock graph --format json`

```json
{"schema_version":1, "root":"/abs", "generated_at":"...",
 "nodes":[{"id":"/abs/dir","label":"train","kind":"run","status":"complete",
           "timestamp":"...","note":null,"target":null,"fingerprint":null,"tag":null,
           "tree_hashes":{"main":"abc"},"data_hashes":{},"metrics":{"acc":0.93}}],
 "edges":[{"source":"/abs/up","target":"/abs/dir","type":"lineage"},
          {"source":"/abs/master","target":"/abs/master/sweep_0000","type":"sweep_item"}],
 "groups":{"same_tree":[["/a","/b"]],"same_data":[]}}
```

`id` is a resolved absolute path. `metrics` are the top-level numeric keys of
`results.json`. Edges pointing outside the scanned tree materialise `kind:
external` stub nodes so the graph is closed. `--groups` adds size-≥2 clusters of
nodes sharing identical tree hashes / data dicts.

### `flexlock why --format json`

```json
{"schema_version":1,"run_a":"/a","run_b":"/b","match":false,
 "diffs":{"config":[...],"git":[...],"data":[...]},
 "commits":{"main":{"trees_identical":false,
   "a_to_b":[{"sha":"...","author":"...","date":"...","subject":"..."}],
   "b_to_a":[],"error":null}}}
```

Per common repo, if the recorded tree hashes match it reports `trees_identical`;
otherwise it walks `git log a..b` / `b..a` between the recorded shadow commits.
gc'd refs yield a per-repo `error` and the command still exits 0.

## Recording intent — `--note`

Always launch runs with a `--note` explaining *why* they exist:

```bash
flexlock-run -d myproject.pipeline.cfg -s train --note "baseline before lr sweep"
```

It's a top-level `run.lock` key, excluded from the fingerprint, surfaced by every
query command. See [Reference › On-Disk Run Files](reference.md#on-disk-run-files).

## Failure records — `run.error`

When a run's user function raises, FlexLock writes a `run.error` JSON sidecar next
to `run.lock` (schema in the [Reference](reference.md#run-error-json-schema-v1)).
Triage a failure without touching sqlite:

```bash
flexlock show <run_dir> --format json    # .error.exc_type / .error.traceback
```

Classify by `exc_type`: user-code errors (fix + re-run with `--force`) vs.
node/infra faults (CUDA `cudaErrorSystemNotReady`, OOM — retry elsewhere). A
successful re-run clears the stale `run.error`.

## Shipped skills

Four Claude Code skills are packaged in the wheel and installable into any project:

```bash
flexlock skills list
flexlock skills install                 # → .claude/skills/
flexlock skills install --force         # upgrade
```

| Skill | Use it to |
|---|---|
| `flexlock-survey` | map a project's experiment state (what ran / failed / is newest) |
| `flexlock-new-stage` | scaffold a new pipeline stage correctly (importability, `_snapshot_`, `pipeline_dir`) |
| `flexlock-run-and-watch` | launch, poll, and triage a run or sweep |
| `flexlock-report` | turn a results tree into a written report + HTML |

## HTML report

```bash
flexlock report results/ -o report.html --title "My experiment"
```

A single self-contained HTML file (inline CSS/JS, no CDN — opens offline on an HPC
login node). It carries a JSON island (`<script id="flexlock-data">`, the same
`graph` payload) as the stable contract for external tooling, a filterable run
table with metric columns, a topological SVG lineage view, and a detail pane that
shows failure tracebacks. `--embed-configs` includes full per-run configs;
`--groups` surfaces runs sharing identical code/data.
