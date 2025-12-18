# FlexLock

**Reproducible, Composable, and Scalable Computational Experiments**

[![Documentation](https://img.shields.io/badge/docs-latest-blue.svg)](https://quentinf00.github.io/flexlock/)
[![PyPI version](https://badge.fury.io/py/flexlock.svg)](https://badge.fury.io/py/flexlock)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

FlexLock is a Python library that makes your computational experiments reproducible, composable, and efficient. It automatically tracks everything (code, config, data), detects when you're rerunning identical experiments (and skips them), and helps you build multi-stage pipelines that just work.

## Why FlexLock?

### The Problem

You're running ML experiments and:
- **Lost track**: "Which hyperparameters gave me that 95% accuracy?"
- **Can't reproduce**: "This worked last week, what changed?"
- **Wasting compute**: Running the same preprocessing 10 times
- **Pipeline chaos**: Multi-stage workflows that break constantly

### The FlexLock Solution

```python
from flexlock import flexcli

@flexcli
def train(lr=0.01, epochs=10):
    # ... your training code ...
    return {"accuracy": accuracy}
```

That's it! You now have:
- ✅ **Automatic tracking**: Code, config, and data snapshots
- ✅ **Smart caching**: Never rerun identical experiments
- ✅ **CLI for free**: `python train.py -o lr=0.1`
- ✅ **Parameter sweeps**: `--sweep "0.001,0.01,0.1" --n_jobs 3`
- ✅ **Perfect reproducibility**: `flexlock diff` shows exactly what changed

## Quick Start

### Install

```bash
pip install flexlock
```

### Example 1: Simple Script

```python
# train.py
from flexlock import flexcli

@flexcli
def train(lr: float = 0.01, epochs: int = 10):
    """Train a model."""
    print(f"Training with lr={lr} for {epochs} epochs")
    # ... training code ...
    return {"accuracy": 0.95}

if __name__ == "__main__":
    train()
```

Run it:

```bash
# Default run
$ python train.py
Training with lr=0.01 for 10 epochs
✓ Results saved to: results/train/run_0001/

# Override parameters
$ python train.py -o lr=0.1 epochs=20

# Parameter sweep (runs 3 experiments in parallel)
$ python train.py --sweep "0.001,0.01,0.1" --sweep-target lr --n_jobs 3
```

### Example 2: Multi-Stage Pipeline

```python
# pipeline.py
from flexlock.api import Project

# Load configurations
proj = Project(defaults='configs.defaults')

# Stage 1: Preprocess
preprocess_result = proj.submit(proj.get('preprocess'))

# Stage 2: Train (uses preprocess output)
train_cfg = proj.get('train')
train_cfg.data_dir = preprocess_result.output_dir
train_result = proj.submit(train_cfg)

# Stage 3: Evaluate
eval_cfg = proj.get('evaluate')
eval_cfg.model_dir = train_result.save_dir
eval_result = proj.submit(eval_cfg)

print(f"Final accuracy: {eval_result.accuracy}")
```

Run it again? FlexLock automatically skips unchanged stages:

```bash
$ python pipeline.py
⚡ Cache Hit! Preprocess already done
⚡ Cache Hit! Training already done
⚡ Cache Hit! Evaluation already done
Final accuracy: 0.95
```

## Key Features

### 🔒 Automatic Reproducibility

Every run creates a snapshot with:
- **Git tree hash**: Exact code state (not just commit)
- **Full configuration**: All parameters used
- **Data fingerprints**: Input data hashes
- **Environment**: System info

Compare any two runs:

```bash
$ flexlock diff run_0001 run_0002
Differences found:
  Config:
    optimizer.lr: 0.001 → 0.01
  Code:
    Git tree: abc123 → def456 (model.py modified)
```

### ⚡ Smart Run Detection

FlexLock never wastes computation. It automatically detects when you're rerunning an experiment with identical inputs and reuses the cached result:

```python
# First run: executes
result1 = proj.submit(config)

# Second run with same config: instant cache hit!
result2 = proj.submit(config)  # ⚡ Skipped!
```

This works even:
- Across different machines (with shared storage)
- Weeks later
- With different result directories (paths are normalized)

### 🔄 Composable Pipelines

Build complex workflows from simple stages:

```python
# Each stage is a function
def preprocess(input_data, output_dir): ...
def train(data_dir, model_type, lr): ...
def evaluate(model_dir, test_data): ...

# Compose them into a pipeline
proj = Project(defaults='configs.defaults')

prep = proj.submit(proj.get('preprocess'))
train_cfg = proj.get('train')
train_cfg.data_dir = prep.output_dir
model = proj.submit(train_cfg)

eval_cfg = proj.get('evaluate')
eval_cfg.model_dir = model.save_dir
results = proj.submit(eval_cfg)
```

Failed at train? Fix it and rerun - FlexLock skips the successful preprocess stage.

### 🚀 Parallel Execution

Run sweeps in parallel automatically:

```python
# Define sweep
sweep = [
    {"lr": 0.001, "batch_size": 32},
    {"lr": 0.01, "batch_size": 32},
    {"lr": 0.1, "batch_size": 64}
]

# Run in parallel (local multiprocessing)
results = proj.submit(config, sweep=sweep, n_jobs=4)

# Or on a cluster (Slurm, PBS)
results = proj.submit(config, sweep=sweep, slurm_config="slurm.yaml")
```

### 📊 Configuration Management

Three ways to configure, all type-safe:

```python
# Method 1: @flexcli (simplest)
@flexcli
def train(lr=0.01, epochs=10): ...

# Method 2: Python configs (most powerful)
from flexlock import py2cfg
config = py2cfg(
    train,
    model=py2cfg(Transformer, layers=12, hidden_size=768),
    optimizer=py2cfg(Adam, lr=0.001),
    epochs=100
)

# Method 3: YAML (declarative)
# config.yaml
train:
  model:
    layers: 12
    hidden_size: 768
  optimizer:
    type: adam
    lr: 0.001
  epochs: 100
```

## Philosophy

FlexLock is built on three principles:

1. **Configuration is Code**: Use Python's full expressiveness or YAML's simplicity
2. **Automatic Reproducibility**: Every run is tracked, no manual logging needed
3. **Smart Execution**: Never rerun identical experiments

Read more in the [Philosophy & Design](https://quentinf00.github.io/flexlock/philosophy.html) docs.

## Documentation

- **[Quickstart Guide](https://quentinf00.github.io/flexlock/quickstart.html)**: Get started in 5 minutes
- **[Tutorials](https://quentinf00.github.io/flexlock/tutorials/)**: Learn by example
  - [01. Basics](https://quentinf00.github.io/flexlock/tutorials/01_basics.html): `@flexcli`, CLI args, sweeps
  - [02. Reproducibility](https://quentinf00.github.io/flexlock/tutorials/02_reproducibility.html): Snapshots, diffs
  - [03. YAML Configs](https://quentinf00.github.io/flexlock/tutorials/03_yaml_config.html): Multi-stage YAML
  - [04. Python Configs](https://quentinf00.github.io/flexlock/tutorials/04_python_config.html): `py2cfg`, nested objects
  - [05. Pipelines](https://quentinf00.github.io/flexlock/tutorials/05_pipeline.html): Multi-stage workflows
- **[User Guide](https://quentinf00.github.io/flexlock/getting_started.html)**: In-depth feature docs
- **[API Reference](https://quentinf00.github.io/flexlock/api.html)**: Complete API documentation

## Installation

### From PyPI

```bash
pip install flexlock
```

### From Conda

```bash
conda install -c quentinf00 flexlock
```

### From Source

```bash
git clone https://github.com/quentinf00/flexlock.git
cd flexlock
pip install -e .
```

## Requirements

- Python 3.8+
- OmegaConf
- Loguru
- PyYAML

## Use Cases

### ✅ Perfect For:

- **ML Research**: Hyperparameter tuning, ablation studies, architecture search
- **Data Science**: Exploratory analysis with automatic tracking
- **Scientific Computing**: Parameter sweeps, reproducible experiments
- **Data Pipelines**: Multi-stage ETL with dependency tracking
- **AutoML**: Large-scale hyperparameter optimization

### ⚠️ Less Suitable For:

- **Production APIs**: Use Flask/FastAPI for serving models
- **Real-time Systems**: FlexLock is for offline experiments
- **Simple One-Off Scripts**: Adds overhead for single-run scripts

## Comparison with Other Tools

| Feature | FlexLock | Hydra | MLflow | DVC |
|---------|----------|-------|--------|-----|
| **Configuration** | Python + YAML | YAML | Code | YAML |
| **Reproducibility** | Automatic | Manual | Partial | Partial |
| **Smart Caching** | ✅ | ❌ | ❌ | ✅ |
| **Multi-stage Pipelines** | ✅ | ❌ | ❌ | ✅ |
| **Parallel Sweeps** | ✅ | ✅ | ❌ | ❌ |
| **Learning Curve** | Low | Medium | Low | High |

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.

## Citation

If you use FlexLock in your research, please cite:

```bibtex
@software{flexlock2024,
  title = {FlexLock: Reproducible, Composable, and Scalable Computational Experiments},
  author = {FlexLock Team},
  year = {2024},
  url = {https://github.com/quentinf00/flexlock}
}
```

## Acknowledgments

FlexLock builds on ideas from:
- **Hydra**: Configuration composition patterns
- **MLflow**: Experiment tracking concepts
- **DVC**: Pipeline dependency tracking
- **Sacred**: Experiment observation patterns

## Support

- **Documentation**: [https://quentinf00.github.io/flexlock/](https://quentinf00.github.io/flexlock/)
- **GitHub Issues**: [Report bugs](https://github.com/quentinf00/flexlock/issues)
- **Discussions**: [Ask questions](https://github.com/quentinf00/flexlock/discussions)

---

Made with ❤️ by the FlexLock team
