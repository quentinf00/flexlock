# MLflow Integration Guide

This guide provides comprehensive coverage of FlexLock's MLflow integration, including the Shadow Run Pattern, best practices, and advanced usage patterns.

---

## Table of Contents

- [Quick Start](#quick-start)
- [The Shadow Run Pattern](#the-shadow-run-pattern)
- [API Reference](#api-reference)
- [Common Workflows](#common-workflows)
- [Advanced Patterns](#advanced-patterns)
- [MLflow UI Filtering](#mlflow-ui-filtering)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Quick Start

### Installation

```bash
pip install mlflow

# or with pixi
pixi add mlflow
```

### Basic Usage

```python
from flexlock import flexcli
from flexlock import mlflow_context
import mlflow

@flexcli
def train(cfg):
    # Your training code
    model = create_model(cfg)
    accuracy = train_model(model, cfg)

    # Log to MLflow
    with mlflow_context(cfg.save_dir, experiment_name="MyExperiment"):
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_artifact("model.pkl")

    return {"accuracy": accuracy}
```

**That's it!** FlexLock automatically:
- ✅ Logs your config from `run.lock`
- ✅ Logs standard artifacts (`experiment.log`, etc.)
- ✅ Manages run lifecycle with Shadow Run Pattern
- ✅ Keeps your MLflow dashboard clean

---

## The Shadow Run Pattern

### The Problem: MLflow Run Management

Traditional MLflow usage creates a dilemma for iterative ML workflows:

**Option 1: Resume Same Run**
```python
# Resume existing run
with mlflow.start_run(run_id="abc123"):
    mlflow.log_metric("new_metric", 0.95)
```

**Problems:**
- 🔴 Old and new metrics get mixed together
- 🔴 Hard to tell which values are current
- 🔴 Can't easily "reset" diagnostic metrics

**Option 2: Create New Run Every Time**
```python
# Create new run
with mlflow.start_run():
    mlflow.log_metric("accuracy", 0.95)
```

**Problems:**
- 🔴 After 50 diagnostic iterations, you have 50 runs
- 🔴 MLflow dashboard becomes cluttered
- 🔴 Hard to find the "current" state of an experiment

### The Solution: Shadow Run Pattern

FlexLock implements **"Always New + Deprecate Old"** strategy:

```
Physical State (Disk):        MLflow Runs (Database):
┌──────────────────┐         ┌─────────────────────────┐
│ outputs/exp/r01/ │◄────────│ Run A (deprecated)      │
│                  │         │ - Config (snapshot)     │
│ • run.lock       │◄────┐   │ - Metrics v1            │
│ • model.pkl      │     │   └─────────────────────────┘
│ • experiment.log │     │
│ • results.json   │     │   ┌─────────────────────────┐
└──────────────────┘     └───│ Run B (ACTIVE) ⭐       │
  (Never moves)              │ - Config (inherited)    │
                             │ - Metrics v2 (latest)   │
                             │ - Model (inherited)     │
                             └─────────────────────────┘
```

**Key Principles:**

1. **Physical Truth**: Data lives in `outputs/exp/run_01` (permanent)
2. **MLflow Truth**: We create a new Run ID every time
3. **The Spotlight**: New run tagged `active`, old run tagged `deprecated`
4. **Artifact Inheritance**: New run re-logs artifacts from disk

**Result:** Your MLflow dashboard shows exactly **one active run per experiment**, always with the latest metrics!

### Shadow Run Lifecycle

```
Iteration 1:
┌─────────────────┐
│ Run A (active)  │  ← First run
│ tag: active     │
└─────────────────┘

Iteration 2:
┌─────────────────┐
│ Run A (depr.)   │  ← Automatically deprecated
│ tag: deprecated │
│ superseded_by:B │
└─────────────────┘
┌─────────────────┐
│ Run B (active)  │  ← New active run
│ tag: active     │
│ supersedes: A   │
└─────────────────┘

Iteration 3:
┌─────────────────┐
│ Run A (depr.)   │
└─────────────────┘
┌─────────────────┐
│ Run B (depr.)   │  ← Also deprecated now
│ superseded_by:C │
└─────────────────┘
┌─────────────────┐
│ Run C (active)  │  ← Latest active run
│ tag: active     │
│ supersedes: B   │
└─────────────────┘
```

**Filter in MLflow UI:** `tags.flexlock.status = 'active'`

You see only Run C (the latest), with all inherited artifacts and latest metrics!

---

## API Reference

### `mlflow_context()`

Context manager for MLflow logging with automatic run management.

```python
from flexlock import mlflow_context

with mlflow_context(
    save_dir: str | Path,
    experiment_name: str = "Default",
    run_name: str = None,
    tags: Dict[str, str] = None,
    log_config: bool = True,
    log_artifacts: bool = True,
) as run:
    # Your MLflow logging code
    mlflow.log_metric("accuracy", 0.95)
    mlflow.log_artifact("plot.png")
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `save_dir` | `str \| Path` | *required* | Directory containing run data (e.g., `outputs/exp/run_01`) |
| `experiment_name` | `str` | `"Default"` | MLflow experiment name |
| `run_name` | `str` | `None` | Name for this MLflow run (defaults to directory name) |
| `tags` | `Dict[str, str]` | `None` | Additional custom tags |
| `log_config` | `bool` | `True` | If True, logs parameters from `run.lock` file |
| `log_artifacts` | `bool` | `True` | If True, logs standard artifacts |

#### Automatic Behaviors

**When `log_config=True`:**
- Reads `save_dir/run.lock`
- Extracts configuration parameters
- Flattens nested config (e.g., `model.lr` → `model.lr`)
- Truncates long strings to 250 characters
- Logs as MLflow parameters
- Logs `run.lock` file as artifact

**When `log_artifacts=True`:**
Automatically logs these files if they exist:
- `experiment.log` - Main experiment log
- `stderr.log` - Standard error output
- `stdout.log` - Standard output

**Tags Added Automatically:**
- `flexlock.dir`: Absolute path to save_dir
- `flexlock.status`: `"active"` (new run) or `"deprecated"` (old run)
- `flexlock.supersedes`: Run ID of previous active run (if exists)
- `flexlock.superseded_by`: Run ID of next run (added to deprecated runs)

#### Returns

Yields `mlflow.ActiveRun` object, or `None` if MLflow not installed.

#### Example

```python
from flexlock import mlflow_context
from pathlib import Path
import mlflow

save_dir = Path("outputs/my_exp/run_01")

with mlflow_context(
    save_dir=save_dir,
    experiment_name="ResNet_Training",
    run_name="resnet50_imagenet",
    tags={"model": "resnet50", "dataset": "imagenet"},
) as run:
    # Log training metrics
    mlflow.log_metric("train_loss", 0.32)
    mlflow.log_metric("val_accuracy", 0.95)

    # Log model
    mlflow.log_artifact("model.pkl")

    # Log plots
    mlflow.log_artifact(save_dir / "learning_curve.png")

    # Access run info
    print(f"Run ID: {run.info.run_id}")
```

---

## Common Workflows

### Workflow 1: Simple Training with Logging

**Scenario:** Train a model and log metrics to MLflow.

```python
from flexlock import flexcli
from flexlock import mlflow_context
import mlflow

@flexcli
def train(cfg):
    """Train a model and log to MLflow."""
    # Training code
    model = build_model(cfg.model)
    history = model.fit(
        train_data,
        epochs=cfg.epochs,
        validation_data=val_data
    )

    # Evaluation
    test_accuracy = model.evaluate(test_data)

    # Save model to disk
    model.save(f"{cfg.save_dir}/model.h5")

    # Log to MLflow
    with mlflow_context(cfg.save_dir, experiment_name="Training"):
        # Metrics
        mlflow.log_metric("test_accuracy", test_accuracy)
        mlflow.log_metric("final_train_loss", history.history['loss'][-1])

        # Model
        mlflow.log_artifact(f"{cfg.save_dir}/model.h5")

    return {"test_accuracy": test_accuracy}
```

**Run:**
```bash
python train.py -c config.yaml

# View in MLflow UI
mlflow ui
```

---

### Workflow 2: Separate Compute and Diagnostics

**Scenario:** Run expensive training once, then iterate on diagnostic plots and metrics.

#### Step 1: Training (Expensive, Run Once)

```python
# train.py
from flexlock import flexcli

@flexcli
def train(cfg):
    """Expensive training - saves to disk, NO MLflow yet."""
    # Long training process
    model = train_for_24_hours(cfg)

    # Save results to disk
    save_results(cfg.save_dir, model, predictions)

    return {"status": "complete"}
```

```bash
# Run once
python train.py -c config.yaml
# Output: outputs/my_exp/2024-01-15_10-30-45/
```

#### Step 2: Diagnostics (Fast, Run Many Times)

```python
# diagnose.py
from flexlock import flexcli
from flexlock import mlflow_context
import mlflow
import matplotlib.pyplot as plt

@flexcli
def diagnose(cfg):
    """Load results and create diagnostic plots."""
    # Load pre-computed results (fast!)
    results = load_results(cfg.save_dir)

    # Generate plots
    fig = create_confusion_matrix(results)
    fig.savefig(f"{cfg.save_dir}/confusion_matrix.png")

    fig2 = create_learning_curves(results)
    fig2.savefig(f"{cfg.save_dir}/learning_curves.png")

    # Calculate metrics
    f1 = compute_f1_score(results)
    precision = compute_precision(results)

    # Log to MLflow
    with mlflow_context(cfg.save_dir, experiment_name="Diagnostics"):
        mlflow.log_metric("f1_score", f1)
        mlflow.log_metric("precision", precision)
        mlflow.log_artifact(f"{cfg.save_dir}/confusion_matrix.png")
        mlflow.log_artifact(f"{cfg.save_dir}/learning_curves.png")
```

```bash
# Point to existing training directory
python diagnose.py save_dir=outputs/my_exp/2024-01-15_10-30-45/

# Tweak plotting code, re-run (creates NEW MLflow run)
python diagnose.py save_dir=outputs/my_exp/2024-01-15_10-30-45/

# Adjust metrics calculation, re-run again
python diagnose.py save_dir=outputs/my_exp/2024-01-15_10-30-45/

# ... iterate 50 times if needed!
```

**MLflow Dashboard:**
- Filter: `tags.flexlock.status = 'active'`
- See: **Exactly 1 run** with latest diagnostics
- Contains: Original config + logs + latest metrics + latest plots

---

### Workflow 3: Hyperparameter Sweeps

**Scenario:** Run parameter sweep and track all experiments.

```python
from flexlock import flexcli
from flexlock import mlflow_context
import mlflow

@flexcli
def train_sweep(cfg):
    """Single training run in a sweep."""
    # Train with current hyperparameters
    model = train_model(cfg)
    val_acc = validate_model(model)

    # Log to MLflow
    with mlflow_context(
        save_dir=cfg.save_dir,
        experiment_name="HPO_Sweep",
        tags={
            "sweep_name": cfg.sweep_name,
            "optimizer": cfg.optimizer,
        }
    ):
        mlflow.log_metric("val_accuracy", val_acc)

        # Tag best run
        if val_acc > cfg.best_acc_threshold:
            mlflow.set_tag("is_best", "true")

    return {"val_acc": val_acc}
```

**Config (sweep.yaml):**
```yaml
sweep_name: lr_optimizer_sweep
model:
  architecture: resnet50
training:
  epochs: 50
  batch_size: 32
best_acc_threshold: 0.90

# Sweep parameters
lr: ???  # To be overridden
optimizer: ???  # To be overridden
```

**Run Sweep:**
```bash
python train_sweep.py -c sweep.yaml \
  -o lr=0.001,0.01,0.1 \
     optimizer=adam,sgd,rmsprop
```

**MLflow Dashboard:**
```
# Filter: All runs in sweep
tags.sweep_name = 'lr_optimizer_sweep'

# Filter: Only best runs
tags.is_best = 'true'

# Filter: Specific optimizer
tags.optimizer = 'adam'
```

**Columns to display:**
- `params.lr`
- `params.optimizer`
- `metrics.val_accuracy`
- `tags.is_best`

---

### Workflow 4: Multi-Stage Pipeline

**Scenario:** Pipeline with preprocess → train → evaluate, all logged to MLflow.

```python
from flexlock import Project
from flexlock import mlflow_context
import mlflow

proj = Project("pipeline.yaml")

# Stage 1: Preprocess (no MLflow)
@proj.register("preprocess")
def preprocess(cfg):
    data = load_and_clean_data(cfg)
    save_data(cfg.save_dir, data)
    return {"num_samples": len(data)}

# Stage 2: Train with MLflow
@proj.register("train")
def train(cfg):
    data = load_data(cfg.save_dir)
    model = train_model(data, cfg)

    with mlflow_context(cfg.save_dir, experiment_name="Pipeline"):
        mlflow.log_metric("train_accuracy", model.train_acc)
        mlflow.log_artifact("model.pkl")

    return {"train_acc": model.train_acc}

# Stage 3: Evaluate with MLflow (same save_dir!)
@proj.register("evaluate")
def evaluate(cfg):
    model = load_model(cfg.save_dir)
    test_acc = model.evaluate(test_data)

    # Creates NEW MLflow run, deprecates training run
    # Inherits config and model.pkl, adds evaluation metrics
    with mlflow_context(cfg.save_dir, experiment_name="Pipeline"):
        mlflow.log_metric("test_accuracy", test_acc)
        mlflow.log_artifact("test_results.json")

    return {"test_acc": test_acc}

# Run pipeline
proj.submit(stage="preprocess", wait=True)
proj.submit(stage="train", wait=True)
proj.submit(stage="evaluate", wait=True)
```

**Result in MLflow:**
- One active run per experiment
- Contains:
  - Config (from preprocess stage)
  - Model (from train stage)
  - Train accuracy (from train stage)
  - Test accuracy (from evaluate stage)
  - Test results (from evaluate stage)

---

## Advanced Patterns

### Pattern 1: Custom Run Names

Use descriptive run names for better organization:

```python
from datetime import datetime

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
run_name = f"{cfg.model_type}_{cfg.dataset}_{timestamp}"

with mlflow_context(
    cfg.save_dir,
    experiment_name="Experiments",
    run_name=run_name,
):
    mlflow.log_metric("accuracy", 0.95)
```

### Pattern 2: Hierarchical Tags

Use dot-separated tags for hierarchical filtering:

```python
with mlflow_context(
    cfg.save_dir,
    tags={
        "project": "image_classification",
        "model.architecture": "resnet50",
        "model.pretrained": "imagenet",
        "data.dataset": "cifar100",
        "data.augmentation": "heavy",
    }
):
    mlflow.log_metric("accuracy", 0.95)
```

**Filter in MLflow UI:**
```
tags.project = 'image_classification' AND tags.`model.architecture` = 'resnet50'
```

### Pattern 3: Conditional Logging

Only log to MLflow in certain conditions:

```python
from flexlock import mlflow_context
import mlflow

@flexcli
def train(cfg):
    model = train_model(cfg)
    accuracy = validate(model)

    # Only log if accuracy exceeds threshold
    if accuracy > cfg.log_threshold:
        with mlflow_context(
            cfg.save_dir,
            experiment_name="Good_Runs",
        ):
            mlflow.log_metric("val_accuracy", accuracy)
            mlflow.log_artifact("model.pkl")

    return {"accuracy": accuracy}
```

### Pattern 4: Manual Parameter Logging

Add runtime parameters not in config:

```python
import git
import platform

with mlflow_context(cfg.save_dir, experiment_name="Training"):
    # FlexLock automatically logs config from run.lock

    # Log additional runtime info
    repo = git.Repo(".")
    mlflow.log_param("git_commit", repo.head.commit.hexsha)
    mlflow.log_param("git_branch", repo.active_branch.name)
    mlflow.log_param("hostname", platform.node())

    # Log metrics
    mlflow.log_metric("accuracy", 0.95)
```

### Pattern 5: Nested Experiments

Organize related experiments hierarchically:

```python
# Parent experiment: Overall project
with mlflow_context(
    cfg.save_dir,
    experiment_name="ImageClassification/ResNet",
    tags={"project": "image_classification"},
):
    mlflow.log_metric("test_accuracy", 0.95)

# Child experiment: Specific variant
with mlflow_context(
    cfg.save_dir,
    experiment_name="ImageClassification/ResNet/Ablations",
    tags={"project": "image_classification", "study": "ablation"},
):
    mlflow.log_metric("ablation_accuracy", 0.92)
```

---

## MLflow UI Filtering

### Essential Filters

**Show only active runs (recommended):**
```
tags.flexlock.status = 'active'
```

**Show deprecated runs:**
```
tags.flexlock.status = 'deprecated'
```

**Show all runs for specific directory:**
```
tags.flexlock.dir = '/absolute/path/to/outputs/exp/run_01'
```

### Advanced Filters

**Runs from a specific sweep:**
```
tags.flexlock.status = 'active' AND tags.sweep_name = 'my_sweep'
```

**Best runs only:**
```
tags.flexlock.status = 'active' AND tags.is_best = 'true'
```

**Runs with specific model:**
```
tags.flexlock.status = 'active' AND tags.model = 'resnet50'
```

**Runs with accuracy above threshold:**
```
tags.flexlock.status = 'active' AND metrics.val_accuracy > 0.90
```

### Tracing Run History

**Find what run A superseded:**
```
tags.flexlock.superseded_by = '<run_A_id>'
```

**Find what superseded run A:**
```
tags.flexlock.supersedes = '<run_A_id>'
```

**Complete lineage:**
```
tags.flexlock.dir = '/path/to/experiment' ORDER BY start_time ASC
```

This shows the complete history: Run A → Run B → Run C → ...

---

## Troubleshooting

### Problem: MLflow Not Installed

**Error:**
```
MLflow not installed. To use mlflow_context, install with: pip install mlflow
```

**Solution:**
```bash
pip install mlflow

# or with pixi
pixi add mlflow
```

**Verify:**
```bash
python -c "import mlflow; print(mlflow.__version__)"
```

---

### Problem: Parameters Not Showing Up

**Symptoms:** No parameters logged in MLflow run

**Possible Causes:**

1. **`run.lock` file doesn't exist**
   ```bash
   ls outputs/my_exp/run_01/run.lock  # Should exist
   ```

   **Solution:** Make sure you're using `@flexcli` decorator or `Project` API

2. **`log_config=False`**
   ```python
   # Wrong
   with mlflow_context(save_dir, log_config=False):  # Disables param logging
   ```

   **Solution:** Use default `log_config=True`

3. **Parameters too long (>250 chars)**

   FlexLock automatically truncates to 250 characters. Check logs:
   ```
   MLflow config logging warning: ...
   ```

---

### Problem: Duplicate Metrics from Multiple Runs

**Symptoms:** MLflow UI shows multiple runs for the same experiment

**Cause:** Creating new `save_dir` for each run instead of reusing

**Wrong:**
```python
from datetime import datetime

@flexcli
def diagnose(cfg):
    # Creates NEW directory each time
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_dir = f"outputs/exp/{timestamp}"  # ❌ New dir every time

    with mlflow_context(save_dir):
        mlflow.log_metric("accuracy", 0.95)
```

**Correct:**
```python
@flexcli
def diagnose(cfg):
    # Reuse EXISTING directory
    save_dir = "outputs/exp/2024-01-15_10-30-45"  # ✅ Same dir

    with mlflow_context(save_dir):
        mlflow.log_metric("accuracy", 0.95)
```

**Result:** Shadow Run Pattern activates, old run gets deprecated

---

### Problem: "Can't Find Previous Run"

**Message in logs:**
```
No previous run found or search failed: ...
```

**This is normal!** On the first run for a directory, there's no previous run to deprecate.

---

### Problem: Deprecated Runs Still Visible

**Issue:** MLflow UI shows both active and deprecated runs

**Solution:** Add filter in MLflow UI:
```
tags.flexlock.status = 'active'
```

**Pro Tip:** Save this filter as a view:
1. Apply filter
2. Click "Save View"
3. Name it "Active Runs Only"

---

### Problem: Artifacts Not Logged

**Symptoms:** Missing `experiment.log` or other artifacts

**Possible Causes:**

1. **Files don't exist in save_dir**
   ```bash
   ls outputs/my_exp/run_01/experiment.log  # Should exist
   ```

2. **`log_artifacts=False`**
   ```python
   with mlflow_context(save_dir, log_artifacts=False):  # Disables artifacts
   ```

   **Solution:** Use default `log_artifacts=True`

3. **Custom artifact names**

   FlexLock auto-logs: `experiment.log`, `stderr.log`, `stdout.log`, `run.lock`

   For custom files, log manually:
   ```python
   with mlflow_context(save_dir):
       mlflow.log_artifact("custom_results.json")
   ```

---

## Best Practices

### ✅ DO

1. **Use descriptive experiment names**
   ```python
   # Good
   with mlflow_context(save_dir, experiment_name="ResNet50_ImageNet"):

   # Bad
   with mlflow_context(save_dir, experiment_name="Exp1"):
   ```

2. **Add meaningful tags**
   ```python
   with mlflow_context(
       save_dir,
       tags={
           "model": "resnet50",
           "dataset": "imagenet",
           "optimizer": "adam",
       }
   ):
   ```

3. **Reuse save_dir for diagnostics**
   ```python
   # Training creates directory
   save_dir = "outputs/exp/run_01"

   # Diagnostics reuse same directory (enables Shadow Run Pattern)
   python diagnose.py save_dir=outputs/exp/run_01
   ```

4. **Filter by active status**
   ```
   tags.flexlock.status = 'active'
   ```

5. **Keep deprecated runs for history**

   Don't delete old runs - they provide audit trail!

### ❌ DON'T

1. **Don't manually manage run resumption**
   ```python
   # Bad - manually managing runs
   existing_run_id = find_run_id(...)
   with mlflow.start_run(run_id=existing_run_id):
       ...

   # Good - let mlflow_context handle it
   with mlflow_context(save_dir):
       ...
   ```

2. **Don't log config parameters twice**
   ```python
   # Bad - already logged automatically
   with mlflow_context(save_dir):
       mlflow.log_param("learning_rate", cfg.lr)  # ❌ Duplicate

   # Good - config auto-logged from run.lock
   with mlflow_context(save_dir):
       mlflow.log_metric("accuracy", 0.95)  # ✅ Just log metrics
   ```

3. **Don't create new directories for diagnostic iterations**
   ```python
   # Bad
   save_dir = f"outputs/exp/diagnostic_{iteration}"  # ❌ New dir

   # Good
   save_dir = "outputs/exp/run_01"  # ✅ Reuse existing
   ```

4. **Don't use mlflow.start_run() directly**
   ```python
   # Bad
   with mlflow.start_run():
       ...

   # Good
   with mlflow_context(save_dir):
       ...
   ```

5. **Don't delete deprecated runs**

   Keep them for history and audit trails!

---

## Summary

FlexLock's MLflow integration provides:

- **Shadow Run Pattern** - Clean dashboard with one active run per experiment
- **Automatic Logging** - Config and artifacts logged from disk
- **Iterative Diagnostics** - Run diagnostics 50 times, see only latest
- **Flexible Filtering** - Powerful tags for organizing experiments

**Key Takeaway:** With `mlflow_context()`, you can separate expensive computation from iterative diagnostics while maintaining a clean, organized MLflow dashboard!

---

## Next Steps

- **HPC Integration**: Scale experiments with [HPC Integration Guide](./hpc_integration.md)
- **Debugging**: Use interactive debugging with [Debugging Guide](./debugging.md)
- **Python API**: See [Python API Reference](./python_api.md) for programmatic usage

---

## Need Help?

- **Issues**: [Report bugs](https://github.com/quentinf00/flexlock/issues)
- **Discussions**: [Ask questions](https://github.com/quentinf00/flexlock/discussions)
- **Docs**: [Full documentation](https://flexlock.readthedocs.io)
