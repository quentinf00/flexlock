# Example 05: The "Orchestrator" (Pipeline & API)

This example demonstrates the **Project API** for orchestrating complex multi-stage pipelines with automatic dependency tracking, parallel execution, and smart resume capabilities.

## What You'll Learn

- Using the `Project` API for workflow orchestration
- Multi-stage pipelines with data dependencies
- Smart resume with `proj.exists()` and `proj.get_result()`
- Hyperparameter sweeps with best model selection
- Passing results between pipeline stages
- Memoization and automatic caching

## Files

- `stages.py` - Individual pipeline stages (preprocess, train, evaluate)
- `configs.py` - py2cfg configurations for each stage
- `pipeline.py` - Pipeline orchestrator using Project API
- `README.md` - This file

## Pipeline Architecture

```
┌─────────────────┐
│  Preprocessing  │  Stage 1: Prepare data
└────────┬────────┘
         │
         v
┌─────────────────┐
│    Training     │  Stage 2: Train model(s)
│    (+ Sweep)    │           Optionally sweep hyperparameters
└────────┬────────┘
         │
         v
┌─────────────────┐
│   Best Model    │  Stage 3: Select best from sweep
│   Selection     │           (if sweep was used)
└────────┬────────┘
         │
         v
┌─────────────────┐
│   Evaluation    │  Stage 4: Evaluate on test data
└─────────────────┘
```

## Prerequisites

```bash
# Install FlexLock
pip install flexlock

# Ensure example 02 data exists (we reuse it)
ls 02_reproducibility/data/train.csv
```

## Demo Scenarios

### Scenario 1: Full Pipeline (First Run)

Run the complete pipeline from start to finish:

```bash
python 05_pipeline/pipeline.py --full
```

**What happens:**
1. **Preprocessing**: Loads raw data, normalizes, saves to `results/pipeline/preprocess/run_0001/`
2. **Training**: Trains model using preprocessed data, saves to `results/pipeline/train/run_0001/`
3. **Evaluation**: Evaluates trained model, saves to `results/pipeline/evaluate/run_0001/`

**Expected output:**
```
Full Pipeline Execution
========================================================

[Stage 1] Preprocessing data...
Stage 1: Data Preprocessing
  Input Data:      02_reproducibility/data/train.csv
  Output Dir:      results/pipeline/preprocess/run_0001
  Normalization:   standard
✓ Preprocessing complete: results/pipeline/preprocess/run_0001

[Stage 2] Training model...
Stage 2: Model Training
  Data Dir:        results/pipeline/preprocess/run_0001
  Model Type:      mlp
  Learning Rate:   0.01
✓ Training complete: results/pipeline/train/run_0001
  Accuracy: 87.00%

[Stage 3] Evaluating model...
Stage 3: Model Evaluation
  Model Dir:       results/pipeline/train/run_0001
✓ Evaluation complete
  Test Accuracy: 84.00%

Pipeline Complete!
========================================================
Preprocessing: results/pipeline/preprocess/run_0001
Training:      results/pipeline/train/run_0001
Evaluation:    results/pipeline/evaluate/run_0001
Final Accuracy: 84.00%
```

**Key concept:** The Project API automatically tracks snapshots for each stage and passes results between stages.

### Scenario 2: Smart Resume (Second Run)

Run the same command again:

```bash
python 05_pipeline/pipeline.py --full
```

**What happens:**
1. **Preprocessing**: `proj.exists()` detects identical config → **SKIPS** re-execution
2. **Training**: Same config detected → **SKIPS**
3. **Evaluation**: Same config detected → **SKIPS**
4. All stages use cached results from first run

**Expected output:**
```
Full Pipeline Execution
========================================================

[Stage 1] Preprocessing data...
✓ Preprocessing already done, skipping...

[Stage 2] Training model...
✓ Training already done, skipping...

[Stage 3] Evaluating model...
✓ Evaluation already done, skipping...

Pipeline Complete!
Final Accuracy: 84.00%
```

**Key concept:** `proj.exists(config)` checks if a run with identical configuration already exists. If so, `proj.get_result(config)` retrieves cached results instantly.

**This is FlexLock's killer feature:**
- No re-computation of expensive stages
- Automatic memoization based on config snapshots
- Works across runs and even across machines (if sharing storage)

### Scenario 3: Hyperparameter Sweep

Run a hyperparameter sweep to find the best model:

```bash
python 05_pipeline/pipeline.py --sweep
```

**What happens:**
1. **Preprocessing**: Runs once (or uses cached result)
2. **Training Sweep**: Trains 4 models with different learning rates/epochs in parallel
3. **Best Selection**: Picks model with highest accuracy
4. **Evaluation**: Evaluates only the best model

**Expected output:**
```
Hyperparameter Sweep Pipeline
========================================================

[Stage 1] Preprocessing data...
✓ Preprocessing already done, skipping...

[Stage 2] Training sweep with 4 configurations...
✓ Sweep complete: 4 models trained

Sweep Results:
  Run 1: lr=0.0010, epochs=10, accuracy=87.00%, loss=0.0909
  Run 2: lr=0.0100, epochs=10, accuracy=88.00%, loss=0.0909
  Run 3: lr=0.0500, epochs=10, accuracy=90.00%, loss=0.0909
  Run 4: lr=0.0100, epochs=20, accuracy=88.00%, loss=0.0476

[Stage 3] Selecting best model...
✓ Best model: Run 3
  Learning Rate: 0.05
  Epochs:        10
  Accuracy:      90.00%

[Stage 4] Evaluating best model...
✓ Evaluation complete

Sweep Pipeline Complete!
========================================================
Models Trained:  4
Best Model:      Run 3
Train Accuracy:  90.00%
Test Accuracy:   87.00%
```

**Key concept:** `proj.submit(config, sweep=grid, n_jobs=2)` runs multiple configurations in parallel, returns all results, then you can select the best programmatically.

### Scenario 4: Model Architecture Comparison

Compare different model types:

```bash
python 05_pipeline/pipeline.py --compare
```

**What happens:**
1. Preprocessing (cached)
2. Trains 3 different model configurations
3. Compares all models
4. Reports winner

**Expected output:**
```
Model Type Comparison
========================================================

[Stage 2] Training 3 model configurations...
✓ Models trained: 3

Model Comparison Results
========================================================

Model 1:
  Type:      linear
  LR:        0.01
  Accuracy:  88.00%
  Loss:      0.0909

Model 2:
  Type:      mlp
  LR:        0.01
  Accuracy:  88.00%
  Loss:      0.0909

Model 3:
  Type:      mlp
  LR:        0.05
  Accuracy:  90.00%
  Loss:      0.0909

========================================================
Winner: Model 3 (mlp)
  Accuracy: 90.00%
```

## Understanding the Project API

### Core Methods

#### `proj.submit(config, sweep=None, n_jobs=1, wait=False)`

Submits a task or sweep for execution.

**Parameters:**
- `config`: Configuration dict (from py2cfg)
- `sweep`: Optional list of override dicts for parameter sweep
- `n_jobs`: Number of parallel workers (default: 1)
- `wait`: If True, blocks until completion and returns results

**Returns:**
- Single result dict (if no sweep)
- List of result dicts (if sweep)

**Examples:**
```python
# Single task
result = proj.submit(train_config, wait=True)

# Sweep
results = proj.submit(train_config, sweep=lr_grid, n_jobs=3, wait=True)
```

#### `proj.exists(config)`

Checks if a run with the given config already exists.

**Returns:** Boolean

**Example:**
```python
if proj.exists(train_config):
    print("Already trained!")
    result = proj.get_result(train_config)
else:
    result = proj.submit(train_config, wait=True)
```

#### `proj.get_result(config)`

Retrieves results from a previously completed run.

**Returns:** Result dict from the cached run

**Note:** Only works if `proj.exists(config)` returns True.

### Pipeline Pattern: Check Before Submit

```python
from flexlock import Project

proj = Project()

# Stage 1
if proj.exists(config1):
    result1 = proj.get_result(config1)
else:
    result1 = proj.submit(config1, wait=True)

# Stage 2 (uses Stage 1 output)
config2.input_dir = result1['output_dir']

if proj.exists(config2):
    result2 = proj.get_result(config2)
else:
    result2 = proj.submit(config2, wait=True)
```

This pattern:
- Skips re-execution of expensive stages
- Works across script invocations
- Enables interactive development

### Passing Data Between Stages

**Method 1: Update config with previous result**
```python
# Stage 1 returns dict with 'output_dir'
preprocess_result = proj.submit(preprocess_config, wait=True)

# Stage 2 config needs that directory
train_cfg = train_config.copy()
train_cfg.data_dir = preprocess_result['output_dir']

# Stage 2 uses Stage 1's output
train_result = proj.submit(train_cfg, wait=True)
```

**Method 2: OmegaConf interpolation (in configs.py)**
```python
# Define dependency in config
train_config = py2cfg(
    train,
    data_dir="${preprocess.output_dir}",  # Placeholder
)

# Pipeline updates before submit
train_cfg.data_dir = preprocess_result['output_dir']
```

### Sweep with Best Selection

```python
# Run sweep
train_results = proj.submit(train_config, sweep=grid, n_jobs=4, wait=True)

# Find best based on metric
best_idx = max(range(len(train_results)),
               key=lambda i: train_results[i]['accuracy'])
best_model = train_results[best_idx]

# Use best in next stage
eval_cfg = eval_config.copy()
eval_cfg.model_dir = best_model['save_dir']
proj.submit(eval_cfg, wait=True)
```

## Advanced Patterns

### Pattern 1: Conditional Pipeline

```python
# Only run expensive stage if needed
if accuracy < 0.9:
    logger.info("Accuracy too low, retraining with more epochs...")
    retrain_cfg = train_config.copy()
    retrain_cfg.epochs = 50
    result = proj.submit(retrain_cfg, wait=True)
```

### Pattern 2: Multi-Branch Pipeline

```python
# Preprocess once
preprocess_result = proj.submit(preprocess_config, wait=True)

# Train multiple model types in parallel
model_types = ['linear', 'mlp', 'transformer']
configs = []
for model_type in model_types:
    cfg = train_config.copy()
    cfg.model_type = model_type
    cfg.data_dir = preprocess_result['output_dir']
    configs.append(cfg)

# Submit all branches
for cfg in configs:
    proj.submit(cfg)  # Async submission

# Wait and compare
# (In practice, you'd use proj.wait_all() or similar)
```

### Pattern 3: Iterative Improvement

```python
# Train → Evaluate → Retrain loop
for iteration in range(5):
    train_cfg.epochs = 10 * (iteration + 1)

    train_result = proj.submit(train_cfg, wait=True)

    eval_cfg.model_dir = train_result['save_dir']
    eval_result = proj.submit(eval_cfg, wait=True)

    if eval_result['accuracy'] > 0.95:
        logger.info(f"Reached target accuracy at iteration {iteration}")
        break
```

## Comparison with Other Approaches

| Approach | Pros | Cons |
|----------|------|------|
| **Bash scripts** | Simple, portable | No memoization, error-prone passing |
| **Makefiles** | Dependency tracking | File-based only, no Python integration |
| **Airflow/Luigi** | Full DAG support | Heavy, requires separate services |
| **FlexLock Project** | Automatic snapshots, memoization, Pythonic | Limited to single-machine (for now) |

## Troubleshooting

### "Config not found" when using get_result()

Always check `proj.exists()` first:
```python
# Wrong
result = proj.get_result(config)  # Might fail

# Right
if proj.exists(config):
    result = proj.get_result(config)
else:
    result = proj.submit(config, wait=True)
```

### Results not cached when they should be

Config snapshots are **content-based**. Even tiny changes create a new snapshot:
```python
config1.lr = 0.01
proj.submit(config1, wait=True)

config2 = config1.copy()
config2.lr = 0.01000001  # Different! Creates new run

proj.exists(config2)  # False
```

### Stage can't find previous stage output

Check file paths in results:
```python
result1 = proj.submit(stage1_config, wait=True)
print(result1)  # Check what keys are available

stage2_config.input = result1['output_dir']  # Use correct key
```

## Best Practices

### 1. Return Structured Results

```python
def stage(input_dir, save_dir):
    # ... do work ...

    return {
        "save_dir": str(save_dir),
        "output_file": str(output_file),
        "metrics": {"accuracy": 0.9, "loss": 0.1},
        "metadata": {...},
    }
```

### 2. Use Smart Resume Everywhere

```python
# At every stage
if proj.exists(config):
    result = proj.get_result(config)
else:
    result = proj.submit(config, wait=True)
```

### 3. Log Pipeline Structure

```python
logger.info("Pipeline Steps:")
logger.info("  1. Preprocess")
logger.info("  2. Train (sweep)")
logger.info("  3. Select best")
logger.info("  4. Evaluate")
```

### 4. Validate Paths

```python
from pathlib import Path

if not Path(result['output_dir']).exists():
    raise FileNotFoundError(f"Expected output not found: {result['output_dir']}")
```

## Next Steps

Try these exercises:

1. **Add a new stage**: Implement a "data augmentation" stage before training
2. **Multi-metric selection**: Select best model based on accuracy AND loss
3. **Ensemble pipeline**: Train multiple models and ensemble their predictions
4. **Cross-validation**: Implement k-fold CV with the Project API

## Related Examples

- **01_basics**: Simple @flexcli scripts
- **02_reproducibility**: Snapshot tracking
- **03_yaml_config**: YAML-based multi-stage configs
- **04_python_config**: py2cfg for nested objects

## Additional Resources

- [FlexLock Project API Documentation](../../flexlock/docs/project.md)
- [FlexLock Parallel Execution](../../flexlock/docs/parallel.md)
- [Snapshot System](../../flexlock/docs/snapshot.md)
