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

### Comparison with Other Tools

| Feature | FlexLock | Hydra | MLflow | DVC | Sacred |
|---------|----------|-------|--------|-----|--------|
| **Configuration** | Python + YAML | YAML + Python | Code | YAML | Python |
| **Reproducibility** | Automatic | Manual | Partial | Partial | Automatic |
| **Smart Caching** | ✅ | ❌ | ❌ | ✅ | ❌ |
| **Multi-stage** | ✅ | ❌ | ❌ | ✅ | ❌ |
| **Parallel Sweeps** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Learning Curve** | Low | Medium | Low | High | Medium |

**FlexLock vs Hydra:**
- FlexLock: Batteries-included reproducibility + pipelines
- Hydra: Powerful config composition, but no built-in tracking

**FlexLock vs MLflow:**
- FlexLock: Experiment orchestration + tracking
- MLflow: Model registry + deployment focus

**FlexLock vs DVC:**
- FlexLock: In-memory pipelines, smart caching
- DVC: Git-like versioning for data

### Getting Started

Ready to try FlexLock? Start with:

1. **[Quickstart Guide](./quickstart.md)**: 5-minute introduction
2. **[Usage Guide](./usage_guide.md)**: Comprehensive usage patterns
3. **[Python API](./python_api.md)**: Programmatic usage with Project class
