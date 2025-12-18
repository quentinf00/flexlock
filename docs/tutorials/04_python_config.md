# Example 04: The "Developer" (Python Config)

This example demonstrates Python-based configuration using `py2cfg`, which allows you to create configuration dictionaries from Python objects with proper type instantiation.

## What You'll Learn

- Creating configs with `py2cfg` for nested objects
- Using `None` pattern for mutable defaults
- Deep parameter overrides on nested objects
- Swapping classes at runtime via configuration
- Difference between py2cfg and @flexcli approaches

## Files

- `components.py` - Functions and classes (Model, Optimizer, train, evaluate)
- `config.py` - Configuration definitions using py2cfg
- `README.md` - This file

## Key Pattern: Mutable Defaults

**Problem:** Mutable defaults in Python are dangerous:
```python
def train(optimizer=Adam()):  # BAD: shared between calls
    ...
```

**Solution:** Use None with py2cfg:
```python
def train(optimizer: Optional[Optimizer] = None):  # GOOD
    if optimizer is None:
        raise ValueError("optimizer must be provided")
    ...

# In config.py
train_config = py2cfg(train, optimizer=py2cfg(Adam, lr=0.001))
```

## Prerequisites

```bash
# Install FlexLock
pip install flexlock

# Ensure example 02 data exists (we reuse it)
ls 02_reproducibility/data/train.csv
```

## Demo Scenarios

### Scenario 1: Defaults Loading

Run training with pre-configured Adam optimizer:

```bash
flexlock-run -d 04_python_config.config.train_adam
```

**What happens:**
1. Loads `train_adam` config from config.py
2. Instantiates `Model(model_type="mlp", hidden_size=128)`
3. Instantiates `Adam(lr=0.001, beta1=0.9, beta2=0.999)`
4. Calls `train(model=..., optimizer=..., ...)`
5. Saves checkpoint to auto-versioned directory

**Expected output:**
```
Training with Python Config
  Model:        Model(type=mlp, hidden_size=128)
  Optimizer:    Adam(lr=0.001, beta1=0.9, beta2=0.999)
  Batch Size:   32
  Epochs:       10
  ...
✓ Training complete | Final Loss: 0.0909
✓ Checkpoint saved: results/python_config/run_0001/checkpoint.txt
```

**Key concept:** py2cfg creates a config dict with `_target_` pointing to the function/class, and FlexLock handles instantiation automatically.

### Scenario 2: Deep Override (Nested Parameters)

Override the learning rate of the nested optimizer:

```bash
flexlock-run -d 04_python_config.config.train_adam -O optimizer.lr=0.05
```

**What happens:**
1. Loads base config (train_adam)
2. Overrides `optimizer.lr` to 0.05 (nested override)
3. Adam is instantiated with new lr: `Adam(lr=0.05, beta1=0.9, beta2=0.999)`
4. Executes training

**Expected output:**
```
Training with Python Config
  Model:        Model(type=mlp, hidden_size=128)
  Optimizer:    Adam(lr=0.05, beta1=0.9, beta2=0.999)  ← lr changed
  ...
```

**Key concept:** `-O` supports nested overrides using dot notation. This works because py2cfg configs are OmegaConf DictConfig objects.

### Scenario 3: Swapping Classes

Replace the Adam optimizer with SGD entirely:

```bash
flexlock-run -d 04_python_config.config.train_adam -O 'optimizer={_target_: 04_python_config.components.SGD, lr: 0.1, momentum: 0.9}'
```

**What happens:**
1. Loads base config (train_adam with Adam optimizer)
2. Replaces entire `optimizer` config with new dict
3. New config has `_target_: 04_python_config.components.SGD`
4. FlexLock instantiates SGD instead of Adam
5. Train receives `SGD(lr=0.1, momentum=0.9)`

**Expected output:**
```
Training with Python Config
  Model:        Model(type=mlp, hidden_size=128)
  Optimizer:    SGD(lr=0.1, momentum=0.9)  ← Completely different class!
  ...
```

**Key concept:** You can swap entire objects by providing a dict with `_target_` pointing to a different class. This is powerful for experimentation.

**Note:** The quotes around the override are important for shell parsing of the dict syntax.

### Scenario 4: Using Alternative Config

Run with the pre-configured SGD setup:

```bash
flexlock-run -d 04_python_config.config.train_sgd
```

**What happens:**
1. Loads `train_sgd` config (already has SGD configured)
2. Executes with SGD optimizer

**Expected output:**
```
Training with Python Config
  Model:        Model(type=mlp, hidden_size=128)
  Optimizer:    SGD(lr=0.01, momentum=0.9)
  ...
```

**Key concept:** You can define multiple named configurations in config.py and select them via `-d`.

### Scenario 5: Sweep Optimizers (Python API)

Run a sweep over different optimizer configurations:

```bash
flexlock-run -d config.defaults -s train_adam --sweep-key optimizer_grid --n_jobs 2
```

**What happens:**
1. Loads `defaults` as base config
2. Select `train_adam` as task config
2. Loads `optimizer_grid` with 4 different optimizer configs:
   - Adam(lr=0.001)
   - Adam(lr=0.01)
   - SGD(lr=0.01, momentum=0.0)
   - SGD(lr=0.01, momentum=0.9)
3. Runs 4 experiments in parallel (n_jobs=2)


**Key concept:** Python API with FlexLockRunner allows programmatic sweeps and result aggregation.

### Scenario 6: Combined Sweep

Run a grid search over multiple parameters:

```bash
flexlock-run 04_python_config.configs.defaults -s train_adam --sweep-key combined
```

**What happens:**
1. Runs 3 configurations combining model size, optimizer, and batch size
2. Finds best configuration based on final loss
3. Reports winner


## Advanced Examples

### Override Multiple Nested Parameters

```bash
flexlock-run -d 04_python_config.config.train_adam \
  -O optimizer.lr=0.02 \
  -O optimizer.beta1=0.95 \
  -O model.hidden_size=256 \
  -O batch_size=64
```

### Use Large Model Config

```bash
flexlock-run -d 04_python_config.config.train_large
```

### Create Custom Config via CLI

```bash
flexlock-run -d 04_python_config.config.train_adam \
  -O 'model={_target_: 04_python_config.components.Model, model_type: cnn, hidden_size: 512}'  epochs=20
```

## Understanding py2cfg

### What py2cfg Does

`py2cfg` creates an OmegaConf DictConfig with a special `_target_` key:

```python
from flexlock import py2cfg
from components import train, Adam, Model

config = py2cfg(
    train,
    model=py2cfg(Model, hidden_size=128),
    optimizer=py2cfg(Adam, lr=0.001),
    epochs=10
)

# Resulting config (conceptually):
{
    "_target_": "04_python_config.components.train",
    "model": {
        "_target_": "04_python_config.components.Model",
        "hidden_size": 128
    },
    "optimizer": {
        "_target_": "04_python_config.components.Adam",
        "lr": 0.001
    },
    "epochs": 10
}
```

### When FlexLock Runs the Config

1. Instantiates innermost objects first (depth-first)
2. `model_instance = Model(hidden_size=128)`
3. `optimizer_instance = Adam(lr=0.001)`
4. Calls `train(model=model_instance, optimizer=optimizer_instance, epochs=10)`

### Comparison: py2cfg vs @flexcli

| Feature | @flexcli | py2cfg |
|---------|----------|--------|
| **Use case** | Simple scripts | Complex object hierarchies |
| **Config source** | Function signature | Explicit Python code |
| **Nested objects** | Not supported | Full support |
| **Type instantiation** | Automatic for simple types | Explicit with py2cfg() |
| **CLI generation** | Built-in | Via FlexLockRunner |
| **Best for** | Quick experiments | Libraries, frameworks |

**Example comparison:**

```python
# @flexcli approach (Example 01, 02)
@flexcli
def train(lr: float = 0.01, epochs: int = 10):
    ...

# py2cfg approach (Example 04)
def train(optimizer: Optional[Optimizer] = None):
    ...

config = py2cfg(train, optimizer=py2cfg(Adam, lr=0.01))
```

## Configuration Hierarchy

When using `flexlock-run -d`, you can still use all override mechanisms:

```bash
flexlock-run \
  -d 04_python_config.config.train_adam \  
  -c additional.yaml \                      # Merge YAML config
  -O optimizer.lr=0.05 \                    # Override nested param
  -O epochs=20                              # Override top-level param
```

## Working with Results

All runs create snapshots just like @flexcli examples:

```bash
# Compare two runs
flexlock-diff dirs results/python_config/run_0001 results/python_config/run_0002 --details

# Check checkpoint
cat results/python_config/run_0001/checkpoint.txt
```

## Troubleshooting

### "optimizer must be provided"

You're trying to call the function directly without config:
```python
# Wrong
from components import train
train()  # Error: optimizer is None

# Correct - use via FlexLock
flexlock-run -d 04_python_config.config.train_adam
```

### Import errors with _target_

Ensure the module path in `_target_` is correct:
```yaml
# Correct
_target_: 04_python_config.components.SGD

# Wrong
_target_: components.SGD  # Missing package prefix
_target_: SGD              # No module path
```

### Override syntax errors

Shell quoting is important for dict overrides:
```bash
# Correct
-O 'optimizer={_target_: path.SGD, lr: 0.1}'

# Wrong (shell parsing issues)
-O optimizer={_target_: path.SGD, lr: 0.1}  # No quotes
```

## Best Practices

### 1. Always Use None for Object Defaults

```python
# Good
def train(optimizer: Optional[Optimizer] = None):
    if optimizer is None:
        raise ValueError("...")

# Bad
def train(optimizer: Optimizer = Adam()):  # Shared mutable default!
```

### 2. Organize Configs by Use Case

```python
# config.py
train_adam = py2cfg(...)      # Default config
train_sgd = py2cfg(...)       # Alternative
train_large = py2cfg(...)     # For large experiments
train_debug = py2cfg(...)     # Fast debug runs
```

### 3. Define Grids for Common Sweeps

```python
# config.py
optimizer_grid = [...]   # Ready-to-use optimizer sweep
model_grid = [...]       # Ready-to-use model sweep
```

### 4. Use Type Hints

Type hints help with:
- Code clarity
- IDE autocompletion
- Documentation

```python
def train(
    model: Optional[Model] = None,
    optimizer: Optional[Optimizer] = None,
    batch_size: int = 32,
) -> Dict[str, Any]:
    ...
```

## Next Steps

Try these exercises:

1. **Add a new optimizer**: Create RMSprop class and add to grid
2. **Deep nesting**: Create a model with nested components (layers, activations)
3. **Conditional configs**: Use OmegaConf interpolation in py2cfg
4. **Validation**: Add config validation before execution

## Related Examples

- **01_basics**: Simple @flexcli decorator pattern
- **02_reproducibility**: Snapshot tracking
- **03_yaml_config**: YAML-based configurations
- **05_pipeline**: Using py2cfg configs in pipelines

## Additional Resources

- [FlexLock py2cfg Documentation](../../flexlock/docs/configuration.md)
- [OmegaConf Documentation](https://omegaconf.readthedocs.io/)
- [FlexLockRunner API](../../flexlock/docs/runner.md)
