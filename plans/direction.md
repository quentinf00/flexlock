# Should FlexLock exist, and in what shape (2026-11-23)

Discussion notes to pick up from. Read with [slim-core.md](slim-core.md) (the census and the
cut-down plan) and [campaign-launcher.md](campaign-launcher.md) (chains across resources).

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
4. **Decide A, B or C** from those two experiments; then rewrite slim-core.md's release table
   accordingly.
5. **sst, independently:** settle its 198 uncommitted files first (last commit 2026-09-08); the rest
   of its migration (slim-core.md §5) waits on the direction.
