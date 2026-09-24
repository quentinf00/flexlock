# Philosophy & Design

## The FlexLock Approach

FlexLock is built on a simple principle: **Configuration is data, experiments should be reproducible, and workflows should be composable.**

### Core Problems FlexLock Solves

1. **Configuration Hell**: Managing hyperparameters across hundreds of experiments
2. **"What did I run?"**: Inability to reproduce results from weeks ago
3. **Workflow Chaos**: Complex multi-stage pipelines that are brittle and hard to modify
4. **Wasted Computation**: Re-running identical experiments because you forgot you already did them

### Design Principles

#### 1. Configuration as Code

FlexLock treats configuration as first-class code:
- **Python configs** (`py2cfg`): Define configs with full Python expressiveness
- **YAML configs**: For simpler, declarative setups
- **CLI overrides**: Quick experimentation without editing files
- **Type-safe**: Leverage Python's type system and OmegaConf's validation

```python
from flexlock import py2cfg

# Configuration is just Python code
train_config = py2cfg(
    train_model,
    model=py2cfg(Transformer, layers=12, hidden_size=768),
    optimizer=py2cfg(Adam, lr=0.001),
    epochs=100
)
```

#### 2. Automatic Reproducibility

Every run is automatically tracked with a snapshot containing:
- **Git tree hash**: Exact code state (not just commit)
- **Configuration**: All parameters used
- **Data hashes**: Input data fingerprints
- **Environment**: System info, dependencies

This means:
- **No manual logging**: It just works
- **Perfect reproducibility**: `flexlock diff` shows exactly what changed
- **Audit trail**: Complete lineage of results

```bash
# Compare two runs - FlexLock tells you exactly what changed
$ flexlock diff run_001 run_002
Differences found:
  Config:
    - optimizer.lr: 0.001 → 0.01
  Code:
    - Git tree: abc123 → def456 (train.py modified)
```

#### 3. Smart Run Detection

FlexLock never wastes computation:
- Automatically detects when a run with identical inputs already exists
- Reuses cached results instead of re-running
- Works across machines with shared storage

```python
# First run: executes
result1 = proj.submit(config)

# Second run with same config: uses cache
result2 = proj.submit(config)  # ⚡ Cache hit! (instant)
```

This turns your workflow into a **pseudo-build system** like Make or Bazel, but for experiments.

#### 4. Composable Pipelines

Build complex workflows from simple stages:
- **Functional**: Each stage is a pure function
- **Dependency-aware**: Outputs feed into next stage
- **Resumable**: Failed stages can be retried
- **Parallel**: Sweeps run in parallel automatically

```python
# Stage 1: Preprocess
preprocess_result = proj.submit(preprocess_config)

# Stage 2: Train (uses Stage 1 output)
train_config.data_dir = preprocess_result.output_dir
train_result = proj.submit(train_config)

# Stage 3: Evaluate
eval_config.model_dir = train_result.save_dir
eval_result = proj.submit(eval_config)
```

### When to Use FlexLock

#### ✅ Perfect For:

- **ML Research**: Hyperparameter tuning, ablation studies, architecture search
- **Data Pipelines**: Multi-stage ETL with dependency tracking
- **Scientific Computing**: Parameter sweeps, reproducible experiments
- **AutoML**: Large-scale hyperparameter optimization

#### ⚠️ Consider Alternatives If:

- **One-off scripts**: FlexLock adds overhead for single-run scripts
- **Real-time systems**: Built for offline experiments, not production serving
- **Web APIs**: Use Flask/FastAPI for serving models

### The FlexLock Stack

```
┌─────────────────────────────────────────────┐
│           Your Research Code                │
│     (models, training loops, analysis)      │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│              FlexLock API                   │
│  • Project (orchestration)                  │
│  • @flexcli (simple scripts)                │
│  • py2cfg (config management)               │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│          Core Services                      │
│  • Snapshot (tracking)                      │
│  • RunDiff (comparison)                     │
│  • ParallelExecutor (sweeps)                │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│            Infrastructure                   │
│  • Local: multiprocessing                   │
│  • Cluster: Slurm, PBS                      │
│  • Containers: Singularity, Docker          │
└─────────────────────────────────────────────┘
```

### Where FlexLock Comes From

FlexLock is the third attempt at one goal: **Hydra's ergonomics** (overrides,
sweeps, callables as config) **with DVC's provenance** (every result traceable
to its code, config and data, and never recomputed needlessly).

1. **Hydra + DVC side by side.** Each is good at its half, but they don't
   share a model of a run. Hydra writes timestamped output dirs; DVC wants
   stages declared in `dvc.yaml` with fixed paths and keeps one `dvc.lock`
   per workspace.
2. **[ZenDag](https://github.com/quentinf00/zendag)** generated `dvc.yaml`
   from a hydra-zen store, discovering inputs and outputs through `${deps:}`
   and `${outs:}` resolvers, with MLflow for tracking. It worked, but every
   change went through two phases (regenerate the DAG, then `dvc repro`),
   every sweep point had to be registered in the store up front, and parallel
   or HPC runs all competed for the single workspace lockfile.
3. **FlexLock** removes the generated DAG. Each run hashes its own inputs
   (config, code tree, data, lockfiles) and stores the hash next to its
   outputs in `run.lock`. The cache key belongs to the run, not the
   workspace, so sweeps and Slurm jobs need no shared lockfile, pipelines are
   plain Python, and any config Hydra-style overrides can produce is cacheable
   without registering it first.

### Comparison with Other Tools

FlexLock's niche is narrow on purpose: **caching and provenance for
Python-configured runs, aware of which code files matter, on a shared HPC
filesystem, with no server.** Other tools cover parts of this, some better.

| | FlexLock | Hydra (+ submitit) | DVC | redun | Snakemake |
|---|---|---|---|---|---|
| Config as Python callables | ✅ `py2cfg` | ✅ via hydra-zen | ❌ params files | ✅ task args | ❌ |
| CLI overrides and sweeps | ✅ | ✅ multirun, Optuna and other sweepers | ✅ `dvc exp run -S`, queue | ❌ | ❌ |
| Skips runs whose inputs are unchanged | ✅ per run | ❌ | ✅ per stage | ✅ per call | ✅ per rule (mtime or checksum) |
| Code identity in the cache key | git tree, narrowed to `_target_` modules | ❌ | files listed as `deps` | hash of task source | rule code and params |
| Environment in the cache key | lockfile hashes | ❌ | only if listed as a dep | ❌ | conda env per rule |
| Slurm / PBS | ✅ pull-based workers | ✅ Slurm via submitit | ❌ | ✅ executors | ✅ |
| Remote storage for outputs | ❌ | ❌ | ✅ `dvc push/pull` | ✅ S3 etc. | ✅ storage plugins |
| Needs a server or daemon | ❌ | ❌ | ❌ | ❌ (optional DB) | ❌ |

**Choose something else when:**
- you need rich config composition (config groups, defaults lists) or
  sweeper plugins: use **Hydra**;
- you need to version and share data and models through remote storage:
  use **DVC**;
- your pipeline is a large file-based DAG that benefits from global
  scheduling: use **Snakemake** or **Nextflow**;
- you want function-level caching with full call-graph lineage: look at
  **redun** or **Pydra**;
- you need dashboards for metrics: use **MLflow** or **W&B**. FlexLock can
  link runs to MLflow (see [MLflow integration](mlflow_integration.md)).

### Getting Started

Ready to try FlexLock? Start with:

1. **[Quickstart Guide](./quickstart.md)**: 5-minute introduction
2. **[Usage Guide](./usage_guide.md)**: Comprehensive usage patterns
3. **[Python API](./python_api.md)**: Programmatic usage with Project class
