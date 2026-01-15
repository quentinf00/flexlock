# Debugging with FlexLock

FlexLock provides powerful debugging tools to help you diagnose issues in your experiments quickly.

## The `@debug_on_fail` Decorator

The `debug_on_fail` decorator is a specialized debugging tool that **injects local variables into your interactive session** when a function fails. This allows you to inspect the exact state when the error occurred.

### Basic Usage

```python
from flexlock import debug_on_fail

@debug_on_fail
def train_model(lr=0.01, epochs=10):
    # Your training code
    data = load_data()
    model = create_model()

    for epoch in range(epochs):
        loss = train_epoch(model, data, lr)
        # Something goes wrong here...

    return model
```

When an exception occurs, the local variables (`data`, `model`, `epoch`, `loss`, etc.) are automatically injected into the caller's scope for inspection.

### Activation

The decorator can be activated in **three ways**:

#### Option 1: Command-line flag (Recommended)

When using `@flexcli`, simply pass the `--debug` flag:

```bash
# Enable debugging with CLI flag
python train.py --debug

# Combine with other options
python train.py --debug -o lr=0.01
```

This automatically sets `FLEXLOCK_DEBUG=true` for you.

#### Option 2: Environment variable

```bash
# Activate debugging
export FLEXLOCK_DEBUG=1

# Or inline
FLEXLOCK_DEBUG=1 python train.py

# Run without debugging (default)
python train.py
```

#### Option 3: In Jupyter/IPython

```python
import os
os.environ['FLEXLOCK_DEBUG'] = '1'

# Now all @flexcli decorated functions will have debug mode active
```

**Accepted values:**
- `FLEXLOCK_DEBUG=1` - Active
- `FLEXLOCK_DEBUG=true` - Active
- `FLEXLOCK_DEBUG=0` - Inactive
- Not set - Inactive (default)

### Interactive Debugging Workflow

#### Step 1: Run with Debug Mode

```bash
# Using CLI flag (recommended)
python train.py --debug

# Or using environment variable
FLEXLOCK_DEBUG=1 python train.py
```

#### Step 2: Exception Occurs

```python
Traceback (most recent call last):
  File "train.py", line 45, in train_model
    loss = train_epoch(model, data, lr)
ValueError: Invalid learning rate: -0.1

--- FLEXLOCK_DEBUG: An exception occurred in train_model: Invalid learning rate: -0.1 ---
--- FLEXLOCK_DEBUG: Locals in 'train_model' at time of error: ['lr', 'epochs', 'data', 'model', 'epoch', 'loss'] ---
--- FLEXLOCK_DEBUG: Injected locals into '__main__'. ---
```

#### Step 3: Inspect Variables in REPL

After the crash, if running in an interactive environment or with a debugger:

```python
>>> # Variables are now available!
>>> print(lr)
-0.1
>>> print(epoch)
5
>>> print(model)
<Model object at 0x...>
>>> print(data.shape)
(1000, 10)
```

### Example: Combined with @flexcli

```python
from flexlock import flexcli, debug_on_fail

@flexcli
@debug_on_fail
def train(
    data_path: str = "data/train.csv",
    lr: float = 0.01,
    epochs: int = 10
):
    """Train a model with debugging support."""

    # Load data
    data = pd.read_csv(data_path)
    print(f"Loaded {len(data)} samples")

    # Create model
    model = LinearModel(input_dim=data.shape[1])

    # Training loop
    for epoch in range(epochs):
        # Simulate training
        predictions = model.forward(data)
        loss = compute_loss(predictions, data['target'])

        # Oops! Bug here
        if epoch == 5:
            raise ValueError(f"Training diverged at epoch {epoch}")

        model.update(loss, lr)

    return model

if __name__ == "__main__":
    train()
```

Run with debugging:

```bash
FLEXLOCK_DEBUG=1 python train.py

# When it crashes:
# - data, model, epoch, predictions, loss are all available
# - You can inspect them in an interactive Python session or debugger
```

### Debug Strategy Control

Control debugging behavior via environment variable:

```bash
# Auto-detect environment (default)
FLEXLOCK_DEBUG_STRATEGY=auto python train.py

# Force PDB post-mortem
FLEXLOCK_DEBUG_STRATEGY=pdb python train.py

# Force variable injection (for notebooks/interactive)
FLEXLOCK_DEBUG_STRATEGY=inject python train.py
```

### Use Cases

#### 1. **Interactive Development**

Develop functions interactively with automatic variable capture:

```python
# In IPython or Jupyter
import os
os.environ['FLEXLOCK_DEBUG'] = '1'

from flexlock import debug_on_fail

@debug_on_fail
def experiment():
    data = expensive_preprocessing()  # Takes 10 minutes
    results = run_experiment(data)    # Crashes here!
    return results

# Try running
experiment()

# After crash, 'data' is available!
# No need to rerun preprocessing
>>> data.shape
(10000, 100)
>>> # Fix the bug and continue...
```

#### 2. **Debugging Long-Running Jobs**

When an experiment crashes after hours:

```bash
# Submit job with debug mode
sbatch --export=FLEXLOCK_DEBUG=1 long_job.sh

# Job crashes at step 500 of 1000
# Variables from step 500 are saved
# Resume from there without rerunning everything
```

#### 3. **Root Cause Analysis**

Inspect the exact state when rare bugs occur:

```python
@debug_on_fail
def training_loop(data, model, config):
    for batch in data:
        # ... complex logic ...
        if some_rare_condition:  # Happens once in 1000 batches
            raise ValueError("Rare bug!")

# When it happens, all variables available for inspection
```

### Important Warnings

⚠️ **Advanced Feature**: `debug_on_fail` modifies Python's frame stack. Use with caution.

⚠️ **Not for Production**: This is a development tool. Never enable in production.

⚠️ **Memory**: Injected variables remain in memory. Be cautious with large objects.

⚠️ **Side Effects**: Only safe for pure functions. Don't use with functions that manage resources (files, network connections).

### Comparison with Other Debugging Tools

| Tool | When to Use | Pros | Cons |
|------|-------------|------|------|
| **`debug_on_fail`** | Interactive development, preserving state | No code changes needed, auto-capture | Requires REPL |
| **`pdb`** | Step-by-step debugging | Full control | Manual breakpoints |
| **`ipdb`** | Interactive debugging | IPython features | Requires installation |
| **Logging** | Production debugging | Safe, permanent | No interactivity |

### Best Practices

#### ✅ Do:

- Use in development and debugging sessions
- Enable only when actively debugging
- Test both with and without debug mode
- Use with interactive environments (IPython, Jupyter)

#### ❌ Don't:

- Enable in production code
- Rely on it for permanent error handling
- Use with functions that manage resources
- Forget to disable it (performance overhead)

### Example: Full Debugging Session

```python
# experiment.py
from flexlock import flexcli, debug_on_fail
import pandas as pd

@flexcli
@debug_on_fail(stack_depth=2)
def analyze_data(
    data_path: str = "data/results.csv",
    threshold: float = 0.5,
    save_dir: str = "${vinc:results/analysis}"
):
    """Analyze experiment results."""

    # Load data
    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} results")

    # Filter
    filtered = df[df['accuracy'] > threshold]
    print(f"Found {len(filtered)} results above threshold")

    # Analyze
    best_model = filtered.loc[filtered['accuracy'].idxmax()]

    # Oops! Bug if filtered is empty
    metrics = compute_metrics(best_model)

    return metrics

if __name__ == "__main__":
    analyze_data()
```

**Debug session:**

```bash
$ FLEXLOCK_DEBUG=1 python experiment.py -o threshold=0.99

Loaded 100 results
Found 0 results above threshold
--- FLEXLOCK_DEBUG: Exception in analyze_data: ... ---
--- FLEXLOCK_DEBUG: Locals: ['data_path', 'threshold', 'df', 'filtered', ...] ---

# Now in Python REPL or crash handler:
>>> filtered
Empty DataFrame
Columns: [accuracy, model_type, ...]
Index: []

>>> threshold
0.99

>>> # Ah! Threshold too high
>>> # Fix and rerun with lower threshold
```

### Alternative: Logging-Based Debugging

For production-safe debugging, use FlexLock's logging integration:

```python
from flexlock import flexcli
from flexlock.utils import log_to_file
from loguru import logger

@flexcli
def train(lr=0.01, save_dir="${vinc:results/train}"):
    with log_to_file(Path(save_dir) / "debug.log"):
        logger.debug(f"Starting with lr={lr}")

        data = load_data()
        logger.debug(f"Loaded {len(data)} samples")

        model = create_model()
        logger.debug(f"Model: {model}")

        # All debug info saved to debug.log
```

See [Logging Documentation](./logging.md) for more on structured logging.

### Summary

The `@debug_on_fail` decorator is a powerful tool for **interactive experiment development**:

- ✅ Automatic variable capture on failure
- ✅ No code changes needed
- ✅ Works with `@flexcli` and other decorators
- ✅ Controlled via environment variable

Use it during development to preserve expensive computation state and debug issues efficiently!
