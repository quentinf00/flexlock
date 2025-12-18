# Example 03: The "Engineer" (Multistage YAML)

This example demonstrates advanced YAML configuration management with FlexLock, including multi-stage configurations, node selection, interpolation, and complex overrides.

## What You'll Learn

- Multi-stage configuration structure
- Node selection with `--select`
- OmegaConf interpolation between stages
- Global parameters shared across stages
- Two-stage overrides (before and after selection)
- Sweep from config keys

## Files

- `main.py` - Defines stage_a and stage_b functions
- `config.yaml` - Multi-stage configuration with global params
- `overrides.yaml` - Example override file for merging
- `README.md` - This file

## Configuration Structure

The `config.yaml` file demonstrates a hierarchical structure:

```yaml
global_params:          # Shared parameters
  seed: 42
  base_dir: "results/yaml_config"

stage_A:                # First stage (preprocessing)
  _target_: ...
  seed: ${global_params.seed}    # Interpolation
  output_dir: ...

stage_B:                # Second stage (training)
  _target_: ...
  input_dir: ${stage_A.output_dir}  # Cross-stage interpolation
  seed: ${global_params.seed}

experiments:            # Sweep configurations
  grid_search: [...]
```

## Prerequisites

```bash
# Install FlexLock
pip install flexlock
```

## Demo Scenarios

### Scenario 1: Selection & Interpolation

Run Stage B while accessing Stage A's configuration:

```bash
flexlock-run -c 03_yaml_config/config.yaml -s stage_B
```

**What happens:**
1. Loads full config from `config.yaml`
2. Selects `stage_B` node
3. `stage_B` accesses:
   - `${stage_A.output_dir}` → Interpolated from stage_A config
   - `${global_params.seed}` → Interpolated from global params
4. Executes `stage_b` function

**Expected output:**
```
Stage B: Model Training
  Input Dir:     results/yaml_config/preprocessed
  Global Seed:   42
  ...
```

**Note:** Stage B can access Stage A's config even if Stage A wasn't run yet. This is OmegaConf interpolation, not lineage tracking.

### Scenario 2: Outer Override (Global Parameters)

Override global parameters before selection:

```bash
flexlock-run -c 03_yaml_config/config.yaml -s stage_B -o global_params.seed=99
```

**What happens:**
1. Loads config
2. **Before selection**: Overrides `global_params.seed` to 99
3. Selects `stage_B`
4. Stage B sees the new seed via interpolation

**Expected output:**
```
Stage B: Model Training
  Global Seed:   99    ← Changed from 42
  ...
```

**Key concept:** `-o` overrides happen **before** `--select`, so they affect the root config.

### Scenario 3: Inner Override (Local Parameters)

Override stage-specific parameters after selection:

```bash
flexlock-run -c 03_yaml_config/config.yaml -s stage_B -O lr=0.5 batch_size=128
```

**What happens:**
1. Loads config
2. Selects `stage_B`
3. **After selection**: Overrides `lr` and `batch_size` in selected node
4. Executes with new values

**Expected output:**
```
Stage B: Model Training
  Learning Rate: 0.5     ← Changed from 0.01
  Batch Size:    128     ← Changed from 32
  ...
```

**Key concept:** `-O` overrides happen **after** `--select`, so they modify the selected node directly.

### Scenario 4: Run Stage A First

Create the output directory that Stage B expects:

```bash
flexlock-run -c 03_yaml_config/config.yaml -s stage_A
```

**Expected output:**
```
Stage A: Data Preprocessing
  Output Dir:    results/yaml_config/preprocessed
  Process Mode:  normalize
  ...
✓ Data processed: results/yaml_config/preprocessed/processed_data.txt
```

Now run Stage B:

```bash
flexlock-run -c 03_yaml_config/config.yaml -s stage_B
```

**Expected output:**
```
Stage B: Model Training
  Input Dir:     results/yaml_config/preprocessed
✓ Found input from Stage A: .../processed_data.txt
  ...
```

### Scenario 5: Sweep from Config Key

Run multiple Stage A experiments using the grid defined in config:

```bash
flexlock-run -c 03_yaml_config/config.yaml -s stage_A --sweep-key experiments.grid_search --n_jobs 3
```

**What happens:**
1. Loads config
2. Selects `stage_A`
3. Loads sweep list from `experiments.grid_search`
4. Runs 3 experiments with different `process_mode` values

**Expected output:**
```
Running sweep with 3 tasks.
...
```

**Results:**
```
results/yaml_config/
├── stage_a_0001/     # process_mode=normalize
├── stage_a_0002/     # process_mode=standardize
└── stage_a_0003/     # process_mode=minmax
```

### Scenario 6: File Merging

Merge override file after selection:

```bash
flexlock-run -c 03_yaml_config/config.yaml -s stage_B -M 03_yaml_config/overrides.yaml
```

**What happens:**
1. Loads config
2. Selects `stage_B`
3. Merges `overrides.yaml` into selected node
4. Executes with overridden values

**Expected output:**
```
Stage B: Model Training
  Model Type:    deep_mlp     ← From overrides.yaml
  Learning Rate: 0.05          ← From overrides.yaml
  Batch Size:    64            ← From overrides.yaml
  ...
```

## Advanced Examples

### Combining Overrides

You can combine multiple override mechanisms:

```bash
flexlock-run \
  -c 03_yaml_config/config.yaml \
  -o global_params.seed=123 \
  -s stage_B \
  -M 03_yaml_config/overrides.yaml \
  -O lr=0.2
```

**Order of operations:**
1. Load base config
2. Override global seed (-o)
3. Select stage_B (-s)
4. Merge overrides.yaml (-M)
5. Override lr (-O)
6. Execute

### Sweep with Custom Target

Sweep learning rates while keeping other params:

```bash
flexlock-run \
  -c 03_yaml_config/config.yaml \
  -s stage_B \
  --sweep "0.001,0.01,0.1" \
  --sweep-target lr \
  --n_jobs 3
```

### Pipeline Execution

Run both stages in sequence:

```bash
# Stage A: Preprocess data
flexlock-run -c 03_yaml_config/config.yaml -s stage_A

# Stage B: Train on preprocessed data
flexlock-run -c 03_yaml_config/config.yaml -s stage_B
```

Stage B will automatically find the output from Stage A via interpolation.

## Understanding Interpolation

### Global Parameters

```yaml
global_params:
  seed: 42

stage_B:
  seed: ${global_params.seed}  # → Resolves to 42
```

Any stage can access global parameters using `${global_params.key}`.

### Cross-Stage References

```yaml
stage_A:
  output_dir: "results/preprocessed"

stage_B:
  input_dir: ${stage_A.output_dir}  # → Resolves to "results/preprocessed"
```

Stages can reference other stages' configurations.

### OmegaConf Resolvers

```yaml
save_dir: "${global_params.base_dir}/stage_a_${vinc:}"
```

FlexLock's custom resolvers work with interpolation:
- `${vinc:}` - Auto-incrementing version numbers
- `${now:%Y%m%d}` - Timestamps
- `${latest:...}` - Latest matching path

## Override Strategies

### When to use `-o` (before select)

Use for **global changes** that affect multiple stages:
```bash
-o global_params.seed=99          # Change seed everywhere
-o global_params.base_dir="exp2"  # Change output location
```

### When to use `-O` (after select)

Use for **stage-specific changes**:
```bash
-O lr=0.1              # Change only this stage's lr
-O model_type="cnn"    # Change only this stage's model
```

### When to use `-m` (merge before select)

Use to **replace entire sections** in root config:
```bash
-m different_globals.yaml  # Replace global_params
```

### When to use `-M` (merge after select)

Use to **update selected stage** with multiple parameters:
```bash
-M tuned_hyperparams.yaml  # Apply pre-tuned config
```

## Common Patterns

### 1. Development Workflow

```bash
# Quick iteration on Stage B
flexlock-run -c config.yaml -s stage_B -O lr=0.05

# Found good params? Save them
cat > best_config.yaml <<EOF
lr: 0.05
batch_size: 128
EOF

# Use saved config
flexlock-run -c config.yaml -s stage_B -M best_config.yaml
```

### 2. Grid Search

```yaml
# In config.yaml
experiments:
  hp_grid:
    - {lr: 0.001, batch_size: 32}
    - {lr: 0.01, batch_size: 32}
    - {lr: 0.01, batch_size: 64}
```

```bash
flexlock-run -c config.yaml -s stage_B --sweep-key experiments.hp_grid --n_jobs 3
```

### 3. Environment-Specific Configs

```yaml
# base_config.yaml
global_params:
  base_dir: "results/local"

# production.yaml
global_params:
  base_dir: "/data/experiments/prod"
```

```bash
# Development
flexlock-run -c config.yaml -s stage_B

# Production
flexlock-run -c config.yaml -m production.yaml -s stage_B
```

## Troubleshooting

### "KeyError: stage_A"

If you get interpolation errors, check that:
1. The referenced stage exists in config
2. The key path is correct
3. You're not trying to access undefined keys

### "Selection returned None"

Check that:
```bash
# Correct
-s stage_B

# Wrong
-s stageB  # No underscore
-s stage-B  # Hyphen instead of underscore
```

### Stage B can't find Stage A output

This is expected if Stage A wasn't run yet. Two options:

**Option 1:** Run Stage A first
```bash
flexlock-run -c config.yaml -s stage_A
flexlock-run -c config.yaml -s stage_B
```

**Option 2:** Override input_dir
```bash
flexlock-run -c config.yaml -s stage_B -O input_dir="some/other/path"
```

## Next Steps

Try these exercises:

1. **Add a new stage**: Create `stage_C` that uses output from `stage_B`
2. **Custom experiment grid**: Define your own sweep in `experiments`
3. **Environment configs**: Create dev/staging/prod override files

## Related Examples

- **01_basics**: Simple CLI and sweeps
- **02_reproducibility**: Snapshot tracking
- **04_python_config**: Python-based configuration
- **05_pipeline**: Automated multi-stage pipelines

## Additional Resources

- [FlexLockRunner Documentation](../../flexlock/docs/runner.md)
- [OmegaConf Documentation](https://omegaconf.readthedocs.io/)
- [flexlock-run CLI](../../flexlock/docs/runner.md#standalone-cli-flexlock-run)
