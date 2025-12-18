# Example 06: Interactive Debugging

This example demonstrates FlexLock's `@debug_on_fail` decorator for preserving computation state when errors occur.

## What You'll Learn

- Using `@debug_on_fail` for automatic variable capture
- Environment-based activation with `FLEXLOCK_DEBUG`
- Integration with `@flexcli` decorator
- Preserving expensive computation state
- Interactive debugging workflows

## Files

- `debug_example.py` - Example script with debugging support
- `README.md` - This file

## The Problem

You're running an expensive analysis:

```python
def analyze():
    data = expensive_preprocessing()  # Takes 1 hour
    results = complex_analysis(data)  # Crashes here!
    return results
```

**Without debugging tools**: You have to rerun the 1-hour preprocessing every time you fix a bug.

**With `@debug_on_fail`**: The expensive `data` is automatically preserved in your scope when the crash occurs.

## The Solution

```python
from flexlock import debug_on_fail

@debug_on_fail
def analyze():
    data = expensive_preprocessing()  # Takes 1 hour
    results = complex_analysis(data)  # Crashes here!
    return results

# Run with: FLEXLOCK_DEBUG=1 python script.py
# After crash, 'data' is available in your REPL!
```

## Prerequisites

```bash
# Install FlexLock
pip install flexlock
```

## Demo Scenarios

### Scenario 1: Normal Run (No Debugging)

Run without debugging:

```bash
python debug_example.py
```

**Expected output:**
- Normal execution
- No variable injection
- Clean crash if error occurs

### Scenario 2: Basic Debugging

Enable debugging mode:

```bash
# Method 1: Using --debug flag (recommended)
python debug_example.py --debug

# Method 2: Using environment variable
FLEXLOCK_DEBUG=1 python debug_example.py
```

**Expected output:**
- Execution completes normally
- Debug mode is active (but no crash, so no injection)
- Logs show completion

### Scenario 3: Debug with Bug (High Threshold)

Trigger a bug by setting threshold too high:

```bash
# Method 1: Using --debug flag
python debug_example.py --debug -o threshold=0.99

# Method 2: Using environment variable
FLEXLOCK_DEBUG=1 python debug_example.py -o threshold=0.99
```

**What happens:**

1. **Phase 1**: Data loading completes (1 second simulated)
2. **Phase 2**: Filters results
3. **Crash**: No results above threshold=0.99
4. **Variable Injection**: All local variables become available

**Expected output:**
```
[Phase 1] Loading and preprocessing data...
✓ Loaded 100 experiment results

[Phase 2] Filtering results (threshold=0.99)...
✓ Found 0 results above threshold

--- FLEXLOCK_DEBUG: An exception occurred in analyze_experiment: No results above threshold 0.99 ---
--- FLEXLOCK_DEBUG: Locals in 'analyze_experiment': ['num_samples', 'threshold', 'results', 'filtered_results', ...] ---
--- FLEXLOCK_DEBUG: Injected locals into '__main__'. ---

ValueError: No results above threshold 0.99. Max accuracy in dataset: 0.982
```

**Now in a Python REPL:**

```python
# Start Python after the crash
>>> import debug_example
>>> FLEXLOCK_DEBUG=1 python debug_example.py -o threshold=0.99
# ... crash occurs ...

# Variables are now available!
>>> results  # The full dataset (100 items)
[{'id': 0, 'accuracy': 0.75, ...}, ...]

>>> filtered_results  # Empty list
[]

>>> threshold  # The problematic value
0.99

>>> # Find the max accuracy
>>> max(r['accuracy'] for r in results)
0.982

>>> # Ah! Threshold is too high. Fix and rerun with threshold=0.7
```

**Key benefit**: No need to rerun the expensive data loading!

### Scenario 4: Random Failure

Trigger random failures to simulate intermittent bugs:

```bash
# Method 1: Using --debug flag
python debug_example.py --debug -o fail_probability=0.5

# Method 2: Using environment variable
FLEXLOCK_DEBUG=1 python debug_example.py -o fail_probability=0.5
```

**What happens:**
- 50% chance of random failure during analysis
- When it fails, all computation up to that point is preserved
- Variables: `results`, `filtered_results`, `best_result`, `statistics` all available

### Scenario 5: Interactive Development

Use in IPython or Jupyter for interactive development:

```python
# In IPython/Jupyter
import os
os.environ['FLEXLOCK_DEBUG'] = '1'

from debug_example import risky_computation

# Try the function
risky_computation(10, 0, 5)  # Division by zero!

# After crash, inspect variables:
x  # 10
y  # 0
z  # 5
intermediate_result  # 20
another_value  # 25
# final_result not available (crashed before assignment)

# Fix and retry:
risky_computation(10, 2, 5)  # ✓ Works!
```

## How It Works

### 1. Decorator Activation

The `@debug_on_fail` decorator checks the `FLEXLOCK_DEBUG` environment variable:

```python
@debug_on_fail
def my_function():
    # Only injects variables if FLEXLOCK_DEBUG=1
    pass
```

**Activation methods:**

1. **CLI flag with @flexcli** (Recommended):
   ```bash
   python script.py --debug
   ```
   When using `@flexcli`, the `--debug` flag automatically activates debug mode.

2. **Environment variable**:
   ```bash
   FLEXLOCK_DEBUG=1 python script.py
   ```

3. **In Jupyter/IPython**:
   ```python
   import os
   os.environ['FLEXLOCK_DEBUG'] = '1'
   ```

**Accepted values:**
- `FLEXLOCK_DEBUG=1` → Active
- `FLEXLOCK_DEBUG=true` → Active
- `FLEXLOCK_DEBUG=0` → Inactive
- Not set → Inactive (default)

### 2. Variable Injection

When an exception occurs:

```python
@debug_on_fail
def analyze():
    data = load_data()      # Completes
    results = process(data) # Completes
    final = compute(results) # Crashes here!
```

**After crash:**
- `data` → Available in caller scope
- `results` → Available in caller scope
- `final` → Not available (assignment never happened)

### 3. Stack Depth Control

#### Automatic Integration with @flexcli

When using `@flexcli` with the `--debug` flag, stack depth is handled automatically:

```python
from flexlock import flexcli

@flexcli
def my_function():
    # Stack depth automatically set to 2 when --debug is used
    pass

# Run with: python script.py --debug
```

No need to manually add `@debug_on_fail` - it's applied automatically!

#### Manual Control

For manual control or when not using `@flexcli`, use `stack_depth` parameter:

```python
from flexlock import flexcli, debug_on_fail

# Without @flexcli: stack_depth=1 (default)
@debug_on_fail
def my_function(): pass

# With @flexcli but calling directly: stack_depth=2
@flexcli
@debug_on_fail(stack_depth=2)
def my_function(): pass
```

**Why?** Each decorator adds a frame. You need to inject variables into the right frame (usually the main/caller frame).

## Common Patterns

### Pattern 1: Long-Running Experiments

```python
@flexcli
@debug_on_fail(stack_depth=2)
def train_model(epochs=100):
    # Phase 1: Expensive data loading
    data = load_and_preprocess()  # 30 minutes

    # Phase 2: Model setup
    model = create_large_model()   # 10 minutes

    # Phase 3: Training
    for epoch in range(epochs):
        loss = train_epoch(model, data)  # Might crash here!

    return model

# Run: FLEXLOCK_DEBUG=1 python script.py
# If crash occurs, 'data' and 'model' are preserved!
```

### Pattern 2: Data Analysis Pipeline

```python
@debug_on_fail
def analyze_results(experiment_dir):
    # Load all experiment results (slow)
    results = load_experiments(experiment_dir)  # 5 minutes

    # Filter and aggregate
    filtered = filter_results(results, threshold=0.8)

    # Statistical analysis (might have bugs)
    statistics = compute_statistics(filtered)  # Crashes sometimes

    return statistics

# With FLEXLOCK_DEBUG=1, 'results' and 'filtered' preserved on crash
```

### Pattern 3: Interactive Development

```python
# In Jupyter notebook
%env FLEXLOCK_DEBUG=1

from mylib import debug_on_fail

@debug_on_fail
def experiment_step1():
    # Try different approaches interactively
    data = expensive_operation()
    result = risky_transformation(data)
    return result

# Run and iterate
experiment_step1()  # Crash? No problem, 'data' is preserved!
```

## Best Practices

### ✅ Do:

- **Use in development**: Enable during active debugging sessions
- **Interactive environments**: IPython, Jupyter, or with a debugger
- **Expensive computations**: Preserve state from long-running operations
- **Test both modes**: Verify code works with and without debug mode

### ❌ Don't:

- **Production code**: Never enable `FLEXLOCK_DEBUG` in production
- **Resource management**: Don't use with functions managing files/connections
- **Forget to disable**: Remove debug mode for final runs
- **Rely permanently**: Use proper error handling in production

## Debugging Checklist

When a crash occurs with `FLEXLOCK_DEBUG=1`:

1. **Identify the crash location** from the traceback
2. **Check injected variables** listed in debug output
3. **Inspect variable values** in a REPL or debugger
4. **Understand the failure** using preserved state
5. **Fix the bug** in your code
6. **Rerun** (expensive computations are skipped if preserved)

## Alternative: Logging

For production-safe debugging, use FlexLock's structured logging:

```python
from flexlock import flexcli
from flexlock.utils import log_to_file
from loguru import logger

@flexcli
def train(save_dir="${vinc:results}"):
    with log_to_file(Path(save_dir) / "debug.log"):
        logger.debug("Starting training")
        logger.debug(f"Data shape: {data.shape}")
        logger.debug(f"Model config: {model.config}")
        # All debug info saved to file
```

See the [Debugging Documentation](../../docs/debugging.md) for comprehensive guide.

## Troubleshooting

### Variables Not Available

**Problem**: Variables not appearing after crash.

**Solutions**:
1. Check `FLEXLOCK_DEBUG=1` is set
2. Verify decorator is applied: `@debug_on_fail`
3. Adjust `stack_depth` if using multiple decorators
4. Ensure running in interactive environment

### Wrong Stack Depth

**Problem**: Variables injected into wrong scope.

**Solution**: Adjust `stack_depth` parameter:

```python
# Too shallow: stack_depth=0
@debug_on_fail(stack_depth=0)  # Variables stay in function

# Just right: stack_depth=1 (default)
@debug_on_fail  # Variables go to caller

# Deeper: stack_depth=2
@flexcli
@debug_on_fail(stack_depth=2)  # Skip @flexcli wrapper
```

### Memory Issues

**Problem**: Large datasets consuming memory.

**Solution**:
- Manually delete large variables when done: `del data`
- Use checkpointing for very large datasets
- Consider logging instead for production

## Summary

The `@debug_on_fail` decorator:

- ✅ **Preserves state** when errors occur
- ✅ **Zero overhead** when disabled (default)
- ✅ **Environment-controlled** via `FLEXLOCK_DEBUG`
- ✅ **Composable** with `@flexcli` and other decorators

Perfect for:
- **Interactive development** in IPython/Jupyter
- **Long-running experiments** where rerunning is expensive
- **Debugging rare bugs** that are hard to reproduce

Use it to speed up your development workflow and debug experiments efficiently!
