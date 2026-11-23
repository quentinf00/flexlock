# FlexLock slim core: plan (draft for review, 2026-11-23)

> Option A of [direction.md](direction.md), which also weighs a smaller provenance kernel (option B)
> against the alternatives (Hydra, submitit, DVC, Prefect, ClearML, Snakemake). The census, the
> layout (§4) and the sst analysis (§5) apply to every option.
>
> **Superseded for the release order:** option B with Python configs kept is now the working plan,
> in [kernel-plan.md](kernel-plan.md). Its step table replaces §6 below.

FlexLock stays public with its docs site. It has never been announced, so removed parts go
without a deprecation release. Scope after the cut: **write configs and stages, run them
(single, pipeline, sweep; parallel or sequential), record what ran, and read the record back.**
Cross-run views move to XPCC; run lifecycle (stale runs, archive) to ACDM.

Evidence: four read-only audits of v0.10.1 (commit 4ee4c99), the projects maxss-nf, hafs-jepa,
sst and maxss-ml (archived), about 150 Claude and Codex transcripts of the last 60 days, and 642
run records under `/scale/project/lops-siam-hurricane-forecast/analysis` changed since 2026-11-10.
Scan scripts and lists: the session scratchpad (`scan.py`, `tx2.py`, `locks.txt`, `dbs.txt`,
`all.json`, `launches.txt`).

## 1. What the census found

- **`Project` (api.py) is the execution engine, not a query API.** `runner.py` (flexlock-run,
  sweeps, pipelines, `--check`) goes through `Project.submit`, `submit_pipeline` and `check`; sst's
  11 launchers, hafs-jepa's pipeline and maxss-nf's tests call it directly. Keep it, slimmed. The
  query layer is `query.py` and `index.py`.
- **Real use is narrow.** `flexlock-run` about 450–720 calls in 60 days; options `-d -s -o -c -m
  --slurm-config --print-job-id --note --save-dir-policy --check --print-config --dry-run --after`,
  sweep flags rarely. The `flexlock` inspection CLI: single digits per subcommand (`show` 7,
  `skills` 8). mlflow, PBS, `status/diff/export` scripts, report: about zero.
- **Agents almost never use the sweep API for campaigns** (2 of about 35 campaigns). Nobody
  rejected it after trying; the reasons are structural (section 3).
- **Bookkeeping is cluttered and has real bugs** (section 4): Slurm logs overwritten on reruns,
  sweep masters never marked complete, records written 0600, SQLite in WAL mode on NFS.

## 2. Modules: keep, shrink, drop

About 14,700 Python lines → about 9,600 (−35%), plus 252 lines of HTML and 4 skills.

| Verdict | Modules |
|---|---|
| keep | flexcli, freeze, sweep_compile, load_stage, config, exceptions, save_dir, destination_guard, queue_refs, parallel, taskdb, worker, worker_cli, backends/slurm + base + dependencies, snapshot, git_utils, fingerprint, data_hash, run_record, record, outputs, runner, run_cli |
| shrink | api (`Project`: load, select, submit, submit_pipeline, check; drop PBS preview, `debug_on_fail`, `link_run`), utils, resolvers (drop `${run:}`, 0 uses), presets (keep make/attach/freeze; drop lookup through the index) |
| drop | query, index, registry, cli (the `flexlock` inspection script), report + HTML, mlflow, debug, status_cli, diff, diff_cli, export, context (dead), backends/pbs, skills/ |

Options: keep `--print-config` and `--merge` (used). Drop `--enqueue`, `--dump`, `-M`, `--debug`,
`--pbs-config`. Replace `--n_jobs` with an explicit `--workers N` (the two docs contradict each
other on `n_jobs` today).

A small `flexlock` command stays, with three subcommands:
- `flexlock --version` (the template's runs.md already tells agents to run it);
- `flexlock status <run>`: one call that shows the record, state, the task errors of a sweep and
  the log paths, so agents stop opening `run.lock.tasks.db` with raw sqlite3;
- `flexlock migrate-layout <dir>` for section 4.

**Minimal reader** (`flexlock.record`): `load_record`, `read_lock`, `list_task_records`,
`load_task_record`, `status(run)` (replaces `read_marker`/`marker_db`), `validate_outputs`.
sst and the maxss bindings need the task-record functions.

## 3. Sweeps: why agents don't use them, and what changes

About 35 multi-run campaigns in 60 days: shell loops over `flexlock-run --print-job-id` (≈13),
custom Python launchers (≈6), raw sbatch or arrays (≈7), `Project.submit_pipeline` one arm per call
(sst, ≈3), arms looped inside one stage (≈3), parallel separate calls (≈3), sweep API **2**.

Reasons, by frequency:
1. **Per-arm chains on mixed resources** (≈12): train on GPU → extract → probe on CPU, each
   `--after` its own parent. A sweep item runs its stages in one allocation with one profile.
2. **Per-arm job IDs** for ledgers and XPCC ORDER `jobs:` lines (all FlexLock campaigns). A sweep
   prints one job ID.
3. **Arms already written as config attributes or stages** (`cfg_a`, `cfg_b`, `train_{arm}`), not
   as sweep items (≈8).
4. **The instructions steer away from sweeps.** The template's `runs.md` never mentions them;
   maxss-nf `docs/workflow.md:108-114` prescribes separate stages with `--after` and a hand-kept
   ledger.
5. Workers and arrays are unclear in the docs; failures hide in the task database.

Changes (0.12):
- **Sweeps chain per stage.** `--stage-profile train=slurm_gpu.yaml probe=slurm_cpu.yaml` compiles
  each stage into a Slurm array; array index *i* of stage *k+1* depends on index *i* of stage *k*
  (`aftercorr`). `--after-sweep <root>` for a readout over the whole sweep.
- **Every accepted job ID printed and kept.** With `--print-job-id`, print one line per item and
  stage (`<job>_<i>`), and write `<root>/.flexrun/jobs.jsonl` (item, stage, job id, log path). This
  replaces the hand-kept ledgers and is what XPCC reads.
- **Sweep over existing configs.** `-d mod:cfg_a,mod:cfg_b` or `-d 'mod:cfg_*'` as items.
- `--workers N` shows as `#SBATCH --array=0-(N-1)` in `--dry-run`; `flexlock-worker --print-job-id`.
- Docs: a "Campaigns" section in the template's `runs.md`, the rule "don't loop `flexlock-run` over
  arms" with the exception spelled out, and the xpcc-orders skill accepts a sweep root as `jobs:`.

## 4. Run-directory layout

Today a task dir holds 4–7 bookkeeping files. A sweep master holds the record, task DB, a YAML
dump of it, a controller lock, a `.flexlock/` index and 5 files per Slurm submission (78 separate
index dirs under the analysis trees).

Bugs to fix whatever the layout (0.10.2):
- **Slurm logs overwritten.** Non-array jobs all write `slurm_logs/slurm.out`; a rerun truncates the
  failed job's log, so XPCC's tick reads the wrong error. Use `%x-%j.out`.
- **Records are 0600** (`NamedTemporaryFile`) in group-shared dirs. Honour the umask (0644).
- **Hash cache in SQLite WAL mode on NFS** (`~/.cache/flexlock/hashes_v2.db`): corrupted on
  2026-11-21/22, killing jobs 3957179 and 3957187. Use the DELETE journal on GPFS or a node-local
  cache, and quarantine and rebuild on "malformed" instead of failing the job.
- **Sweep masters never get `run.complete`**: XPCC artifacts on a sweep root never turn ready.
  Mark the master complete when all its tasks are.

New layout (0.11):

```
<run>/run.complete      # the one visible marker (also on sweep masters)
<run>/.flexrun/         # not ".flexlock", which meant an index scope
    record.yaml         # was run.lock
    status.json         # state, task id, db pointer, job ids, log paths (was .flexlock_marker, .flexlock-queue.json)
    error.json          # was run.error
    outputs.json        # was run.outputs.json
    controller.lock
    jobs.jsonl          # accepted jobs (section 3)
    queue/tasks.db      # sweep master only; the tasks.yaml dump goes
    jobs/<hex>/         # job.slurm, payload.pkl, main.py
    logs/%x-%j.out|err  # unique per job
```

`load_record` reads the old names for one release; `flexlock migrate-layout` rewrites old dirs.
Readers to update:
- **XPCC:**
  - `tick.py` `rerun_of`: match on JobName + WorkDir + dirname(StdOut), because StdOut becomes unique;
  - `autopilot/triage.md`: point at `.flexrun/`;
  - attempts that list `run.lock` as an artifact.
- **ACDM:** `walk.py` (detect runs by `.flexrun/record.yaml`) and `sensors/runs.py` (state from
  `status.json`).
- **maxss and sst bindings:** use `record.status()`.
- **hafs-jepa:** 21 scripts that write their own `run.complete` rename it (e.g. `train.complete`).

## 5. sst

sst (`251218_sst/sst_ml_zarrpatch`) is not on the template, and has no commit since 2026-09-08,
with 198 modified or untracked files, including all of `workflows/`, the launchers and the FlexLock
migration. That comes first.

Today:
- **Launchers:** 11 near-duplicate `scripts/submit_*.py`, each calling `Project.submit_pipeline`
  per arm, pinned to FlexLock ==0.10.0.
- **Second provenance layer:** `source_guard.py` / `SST_FOUNDATION_SOURCE_STATE` re-hashes the
  source at submission. This is a real FlexLock gap: FlexLock snapshots the source at worker start.
- **Ledgers:** `accepted-submissions.jsonl` and `submission.json` repeat the job ids already in
  `run.lock`, in XPCC and in TODO prose.
- **Status checks:** sqlite and sacct checks rewritten in each session.
- **Profiles:** 76 Slurm profiles.
- **Plans:** `plans/TODO.md` (1,632 lines) used as a journal, with `.bak` copies.
- **Stale instructions:** root `CLAUDE.md` is out of date.

Rethought:
1. **Define:** arms as a sweep over configs (section 3), not a `project.get` loop per arm.
2. **Plan:** the TODO section with an id is the run index; ORDER blocks come from XPCC only.
3. **Launch:** plain `flexlock-run` with `--stage-profile`, about 6 role profiles (cpu-prep,
   gpu-train, gpu-infer, eval), `FLEXLOCK_TAGS=track=…`. FlexLock writes `jobs.jsonl`.
   Submission-time source freezing moves into FlexLock (`--freeze-source`), replacing
   `source_guard.py`.
4. **Track and verify:** the XPCC tick and board; `flexlock status <run>` instead of sqlite.
5. **Evaluate:** unchanged (assessment stages).
6. **Compare:** `xpcc compare`.
7. **Report:** brief, decision and `reports/` per the template.

Migration (about 8–10 days of agent work, mostly low to medium risk): commit or snapshot the 198
files (user decision); relax the pin; adopt the template (layout decision: plans sit at container
level); restructure plans; one launcher, then plain CLI once 0.12 lands; tests off `Project` where
they only load configs; consolidate profiles; upgrade and rerun the 11-stage foundation smoke as
acceptance.

## 6. Releases

> Superseded by [kernel-plan.md](kernel-plan.md) (Releases). Kept for the option A record.

| Release | Content | Consumers |
|---|---|---|
| 0.10.2 (patch) | unique Slurm logs, 0644 files, hash cache journal + quarantine, sweep master `run.complete`, `flexlock --version` | none breaking; projects pick it up with a pin bump |
| 0.11 (breaking) | drops (section 2), `.flexrun/` layout, reader + `flexlock status`, docs rewrite and archive of about 25 dev docs | template v1.3 pin + runs.md; XPCC and ACDM readers; maxss-nf docs (about 25 refs), hafs-jepa (3 docs, 21 `run.complete` writers), sst (1 `flexlock-diff`) |
| 0.12 | sweep campaigns (section 3), `--freeze-source` | template runs.md "Campaigns"; xpcc-orders; sst launcher retired |

Docs: keep philosophy, source_attribution, project_instructions, README, changelog. Rewrite
index, quickstart, usage_guide, workflow_guidelines, agentic_workflows, hpc_integration,
python_api, cli_reference, resolvers, reference, api.rst. Archive the dev plans, migration and
triage notes and old release notes under `docs/archive/` (outside the site's toctree).

## Open decisions

1. sst's 198 uncommitted files: commit them as they are (one snapshot commit on a branch) before
   anything else?
2. Sweep chaining per stage (`--stage-profile`, arrays with `aftercorr`): the largest new feature.
   Go, or keep sweeps single-allocation and only fix job IDs and docs?
3. Release order: 0.10.2 fixes now (they cause real failures today), then 0.11, then 0.12?
4. Name of the hidden folder: `.flexrun/`.
