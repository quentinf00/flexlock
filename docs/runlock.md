# `runlock`: Experiment Tracking

The `runlock` function is the cornerstone of reproducibility in Naga. It creates a `run.lock` file, which is a comprehensive and immutable receipt of your experiment. This file captures everything needed to reproduce your run: the exact configuration, the version of your code, the hashes of your data, and links to previous stages.

## Basic Usage

Here's how to integrate `runlock` into a simple processing script:

```python
from pathlib import Path
from naga import runlock

class Config:
    param = 1
    input_path = 'data/input.csv'
    save_dir = 'results/process'

def main(cfg: Config = Config()):
    # --- Your core logic runs here ---
    # For example, processing data and saving results.
    output_path = Path(cfg.save_dir) / 'output.txt'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("results")
    # --- Core logic ends ---

    # Create the runlock after the process has successfully completed.
    runlock(
        config=cfg,
        runlock_path=Path(cfg.save_dir) / 'run.lock' # (default if save_dir is in config)
    )

if __name__ == '__main__':
    main()
```

Running this script will create a `run.lock` file in `results/process/`. This file is a YAML that contains the resolved configuration used for the run.

## Tracking Code Version

To ensure that you can always trace your results back to the exact code that produced them, `runlock` can track the Git commit of your repositories.

```python
runlock(
    config=cfg,
    repos=['.']  # Tracks the Git commit of the current directory
)
```

If your project involves multiple repositories, you can provide paths to each of them:

```python
runlock(
    config=cfg,
    repos={
        'main_project': '.',
        'shared_library': '../libs/my_lib'
    }
)
```

## Tracking Data

To ensure data provenance, `runlock` can hash your input files and directories.

```python
runlock(
    config=cfg,
    repos=['.'],
    data=[cfg.input_path]  # Hashes the file at cfg.input_path
)
```

You can also provide a dictionary to give meaningful names to your data dependencies:

```python
runlock(
    config=cfg,
    repos=['.'],
    data={
        'raw_dataset': cfg.input_path,
        'validation_set': 'data/validation.csv'
    }
)
```

## Tracking Previous Stages

Complex workflows often involve multiple stages (e.g., preprocessing, training, evaluation). `runlock` allows you to link a run to its predecessors by embedding their `run.lock` files.

```python
runlock(
    config=cfg,
    repos=['.'],
    data=[cfg.input_path],
    prevs=[Path(cfg.input_path).parent] # Path to the directory of the previous stage
)
```

This will look for a `run.lock` file in the parent directory of `cfg.input_path` and embed it in the new `run.lock`. This creates a complete, traceable graph of your experiment pipeline.
