# Naga Usage Examples

This document provides practical examples of how to use the Naga library for different scenarios.

## Basic Example: Simple Data Processing

Here's a simple example of using Naga for a data processing task with separate main and diagnostic functions:

```python
from dataclasses import dataclass
from omegaconf import OmegaConf, MISSING
from pathlib import Path
from datetime import datetime
import pickle
from naga import clicfg, snapshot, runlock, track_data

# Register a resolver for automatic timestamp formatting
OmegaConf.register_resolver('now', lambda s: datetime.now().strftime(s), replace=True)

@dataclass
class Config:
    save_dir: str = "results/processing/${now:%y%m%d-%H%M}"
    input_data: str = "data/input.csv"
    output_data: str = MISSING  # Will be computed from save_dir
    param: int = 1

@runlock
@snapshot(branch="run_logs", message="Data processing run")
@track_data("input_data")
@clicfg
def main(cfg: Config = OmegaConf.structured(Config())):
    # Compute output path if not provided
    if cfg.output_data is MISSING:
        save_dir = Path(cfg.save_dir)
        cfg.output_data = str(save_dir / "processed.csv")
    
    # Create save directory
    save_dir = Path(cfg.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing data with parameter: {cfg.param}")
    print(f"Input: {cfg.input_data}")
    print(f"Output: {cfg.output_data}")
    
    # Your actual processing logic here
    # result = process_file(cfg.input_data, cfg.output_data, cfg.param)
    
    # Example: Save a result that diag() can analyze
    result = {"processed_count": cfg.param * 100, "method": "standard"}
    with open(save_dir / "result.pkl", "wb") as f:
        pickle.dump(result, f)
    
    return cfg, locals()

def diag(cfg):
    # Diagnostic function - separate from computation
    # This allows you to iterate on diagnostics without recomputing
    save_dir = Path(cfg.save_dir)
    
    # Reload results from main()
    with open(save_dir / "result.pkl", "rb") as f:
        result = pickle.load(f)
    
    print(f"Analysis of processing with parameter: {cfg.param}")
    print(f"Processed count: {result['processed_count']}")
    print(f"Method: {result['method']}")
    
    # You can add visualizations and analysis here
    # import matplotlib.pyplot as plt
    # plt.plot(...)
    # plt.savefig(save_dir / "analysis.png")

if __name__ == '__main__':
    cfg, local_vars = main()
    diag(cfg)
```

## Advanced Example: Multi-Stage Pipeline

Here's an example of a multi-stage pipeline using Naga:

```python
from dataclasses import dataclass
from omegaconf import OmegaConf, MISSING
from pathlib import Path
from datetime import datetime
from naga import clicfg, snapshot, runlock, track_data, load_stage

# Register a resolver for automatic timestamp formatting
OmegaConf.register_resolver('now', lambda s: datetime.now().strftime(s), replace=True)

@dataclass
class PreprocessingConfig:
    save_dir: str = "results/preprocessing/${now:%y%m%d-%H%M}"
    raw_data: str = "data/raw"
    processed_data: str = MISSING
    normalize: bool = True

@dataclass
class TrainingConfig:
    save_dir: str = "results/training/${now:%y%m%d-%H%M}"
    processed_data_dir: str = MISSING  # Will be provided by load_stage
    model_path: str = MISSING
    epochs: int = 10

# Preprocessing stage
@runlock
@snapshot(branch="run_logs", message="Preprocessing run")
@track_data("raw_data")
@clicfg
def preprocess(cfg: PreprocessingConfig = OmegaConf.structured(PreprocessingConfig())):
    save_dir = Path(cfg.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    
    if cfg.processed_data is MISSING:
        cfg.processed_data = str(save_dir / "processed")
    
    print(f"Preprocessing raw data: {cfg.raw_data}")
    print(f"Output to: {cfg.processed_data}")
    
    # Your preprocessing logic here
    # preprocess_raw_data(cfg.raw_data, cfg.processed_data, normalize=cfg.normalize)

# Training stage that uses the previous stage's output
@runlock
@snapshot(branch="run_logs", message="Training run")
@load_stage("processed_data_dir")  # Load from previous preprocessing stage
@clicfg
def train(cfg: TrainingConfig = OmegaConf.structured(TrainingConfig())):
    save_dir = Path(cfg.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    
    if cfg.model_path is MISSING:
        cfg.model_path = str(save_dir / "model.pkl")
    
    print(f"Training using data from: {cfg.processed_data_dir}")
    print(f"Model output to: {cfg.model_path}")
    print(f"Epochs: {cfg.epochs}")
    
    # Your training logic here
    # train_model(cfg.processed_data_dir, cfg.model_path, epochs=cfg.epochs)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train()
    else:
        preprocess()
```

## Configuration Override Examples

Here are examples of how to use different configuration override mechanisms:

### 1. Override with a config file

Create a `config.yaml`:
```yaml
save_dir: "results/experiment_001"
param: 42
input_data: "data/special_input.csv"
```

Use it with your script:
```bash
python my_script.py --config config.yaml
```

### 2. Override with dotlist parameters

```bash
python my_script.py -o 'param=100' 'save_dir=results/test_run' 'input_data=data/test.csv'
```

### 3. Combine config file and dotlist overrides

```bash
python my_script.py --config base_config.yaml -o 'param=999'
```

### 4. Use experiments from a config file

Create an `experiments.yaml`:
```yaml
exp1:
  param: 10
  save_dir: "results/exp1"

exp2:
  param: 20
  save_dir: "results/exp2"
  input_data: "data/special.csv"
```

Run specific experiments:
```bash
python my_script.py --config experiments.yaml --experiment exp1
```

## MLflow Integration Example

Here's how to integrate with MLflow using the separate main/diag pattern:

```python
from pathlib import Path
from omegaconf import OmegaConf, MISSING
from dataclasses import dataclass
import pickle
from naga import clicfg, snapshot, runlock, track_data
from naga.mlflow_log import mlflow_log_run

@dataclass
class MlflowConfig:
    save_dir: str = "results/mlflow_exp/${now:%y%m%d-%H%M}"
    param: int = 1

@runlock
@snapshot(branch="run_logs", message="MLflow experiment")
@track_data("input_data") if "input_data" in locals() else lambda f: f
@clicfg
def main(cfg: MlflowConfig = OmegaConf.structured(MlflowConfig())):
    save_dir = Path(cfg.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # Your experiment logic
    result = cfg.param * 2  # Dummy computation
    
    # Save result that diag() can analyze and log to MLflow
    results_data = {"result": result, "param_used": cfg.param}
    with open(save_dir / "results.pkl", "wb") as f:
        pickle.dump(results_data, f)
    
    return cfg, locals()

@mlflow_log_run(
    run_lock_path=lambda cfg: Path(cfg.save_dir) / "run.lock"
)
def diag(cfg):
    # Diagnostic function with MLflow logging
    # This allows you to iterate on logging without recomputing
    save_dir = Path(cfg.save_dir)
    
    # Load results from main()
    with open(save_dir / "results.pkl", "rb") as f:
        results_data = pickle.load(f)
    
    print(f"Analyzing results with parameter: {cfg.param}")
    
    # Log to MLflow
    import mlflow
    mlflow.log_metric("result", results_data["result"])
    mlflow.log_param("param_used", results_data["param_used"])
    
    # Log any artifacts
    # mlflow.log_artifact(save_dir / "some_output_file")

if __name__ == '__main__':
    cfg, local_vars = main()
    diag(cfg)  # This will be wrapped with MLflow logging
```

## Running with Different Execution Modes

Naga supports different execution modes, from interactive development to parallel execution:

### 1. Interactive Development

For interactive development in Jupyter or VSCode:
- Run your script normally: `python my_script.py`
- The decorators will work as expected
- Use the `%` cells in your editor for debugging

### 2. Command-line Execution

For command-line execution with configuration:
```bash
python my_script.py -o 'param=5' 'save_dir=results/final'
```

### 3. Batch Processing

For processing multiple configurations:
```bash
# Run multiple experiments with different parameters
for param in 1 2 3 4 5; do
    python my_script.py -o "param=$param" "save_dir=results/batch_${param}"
done
```

## Troubleshooting

### Common Issues

1. **Decorator Order**: Always place `@runlock` before `@clicfg` to ensure it captures the final configuration.

2. **Save Directory**: Make sure your configuration includes a `save_dir` field, which is used by the decorators.

3. **Git Repository**: The `@snapshot` decorator requires a Git repository to function.

4. **Configuration Keys**: When using `@track_data`, make sure the keys you specify exist in your configuration.

### Environment Variables

For MLflow integration, you can set these environment variables:
```bash
export MLFLOW_TRACKING_URI=file:///path/to/mlflow/server
export MLFLOW_RUN_ID=your-run-id  # For resuming runs
```
