# Naga

Naga is a Python library designed to improve the quality of life when developing ML experiments. It provides a set of decorators and utilities that address common requirements in ML development:

- Easy debugging when scripting
- No cost transition going from script to lib (function)
- Easy exploration of different config
- Lightweight config management
- Automatic versioning of data and source code
- Saving and restoring experiment
- Browsing and comparing results across runs
- From simple case scripting to parallel execution (joblib or slurm)
- Separated computation and diagnostics for iterative development

## Documentation

For complete documentation, please see the [docs/](./docs/) directory:

- [Overview](./docs/README.md)
- [Decorators](./docs/decorators.md)
- [Usage Examples](./docs/examples.md)

## Features

### Configuration Management
- `@clicfg` decorator for CLI configuration capabilities
- Supports OmegaConf for flexible configuration
- Command-line overrides and multi-file configuration

### Source Code Versioning
- `@snapshot` decorator for automatic Git snapshots
- Include/exclude filters for selective versioning

### Data Versioning
- `@track_data` decorator for computing and tracking data hashes
- Support for both files and directories

### State Management
- `@runlock` decorator for creating run.lock files with complete experiment state
- `@load_stage` decorator for loading previous experiment stages

### MLflow Integration
- Track experiments with MLflow
- Support for separate diagnostic functions
- Update past MLflow runs

## Installation

To install Naga, use pip:

```bash
pip install naga
```

## Quick Start

The recommended approach for using Naga is with a separated computation and diagnostics pattern:

```python
from dataclass import dataclass
from omegaconf import OmegaConf
from pathlib import Path
from datetime import datetime
import pickle

# Register a resolver for automatic timestamp formatting
OmegaConf.register_resolver('now', lambda s: datetime.now().strftime(s), replace=True)

@dataclass
class Config:
    save_dir = "results/<my_stage>/${now: %y%m%d-%H%M}"
    param = 1
    # All the parameters for the function go here

def main(cfg: Config = OmegaConf.structured(Config())):
    try: 
        # %% The percent cell allows for interactive execution in IDEs like VSCode or Jupyter console
        save_dir = Path(cfg.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        OmegaConf.resolve(cfg)
        OmegaConf.save(cfg, save_dir / 'config.yaml')  # Save config

        # %% Your main computation logic here
        print(f"Processing with param: {cfg.param}")
        
        # Save results for diagnostic function
        results = {"output": cfg.param * 2, "status": "success"}
        with open(save_dir / "results.pkl", "wb") as f:
            pickle.dump(results, f)
        
    except Exception as e:  # Catch errors when executing full function
        import traceback
        print(traceback.format_exc())  # Print traceback
    finally:
        return cfg, locals()  # Return cfg and locals for diag function

def diag(cfg):
    # Diagnostic and analysis function - separate from computation
    # This allows you to iterate on diagnostics without recomputing
    save_dir = Path(cfg.save_dir)
    
    # Load results from main() and perform analysis
    with open(save_dir / "results.pkl", "rb") as f:
        results = pickle.load(f)
    
    print(f"Analyzing results in {save_dir}")
    print(f"Results: {results}")
    # Add visualizations or additional analysis here

if __name__ == '__main__':
    import my_stage
    import importlib as iml; iml.reload(my_stage)  # Reload to avoid restarting the kernel
    
    # Run main computation
    cfg, local_vars = my_stage.main()
    
    # Then run diagnostics
    my_stage.diag(cfg)
    
    # Update kernel state with latest execution locals if needed
    locals().update(local_vars)
```

For more detailed usage examples, see the [Usage Examples](./docs/examples.md) documentation.

## Requirements

- Python 3.7+
- OmegaConf: For configuration management
- GitPython: For source code versioning
- dirhash: For directory hashing
- xxhash: For fast hashing
- mlflow: For experiment tracking (optional)
- pandas: For parameter flattening in MLflow logging