# Naga

Naga is a lightweight Python library designed to bring clarity, reproducibility, and scalability to your computational experiments. It provides a set of explicit, composable tools to handle the boilerplate of experiment tracking, so you can focus on your core logic.

Naga is built on the philosophy that **explicit is better than implicit**. Instead of magical decorators, you use clear, standalone functions and context managers to manage the lifecycle of your run.

## Core Components

- **`naga.clicfg`**: A flexible decorator to handle configuration from both CLI (`--arg value`) and programmatic (`my_func(arg='value')`) calls using OmegaConf.
- **`naga.runlock`**: A function to create a `run.lock` file—a definitive receipt of your experiment containing the config, data hashes, Git commits, and dependencies.
- **`naga.mlflow_lock`**: A context manager that handles the MLflow run lifecycle, including run creation, artifact logging, and logical run management (deprecation of previous runs).
- **Helper Utilities**: Functions like `naga.get_git_commit` and `naga.commit_cwd` for interacting with Git.

## Installation

You can install Naga using `pixi` or `pip` if you manage dependencies manually.

```bash
# With pixi
pixi add naga
```

## Quick Start

Here is a simple example demonstrating the new Naga workflow.

**1. Define your configuration and core logic in a file (e.g., `my_project/main.py`):**

```python
# my_project/main.py
from dataclasses import dataclass
from pathlib import Path
from omegaconf import OmegaConf

@dataclass
class TrainConfig:
    # --- Parameters for the core logic ---
    learning_rate: float = 0.01
    dataset_path: str = "data/raw/iris.csv"
    
    # --- Parameters for Naga ---
    # The save_dir is crucial for Naga to store outputs
    save_dir: str = "/tmp/naga/runs/${now:%Y-%m-%d_%H-%M-%S}"
    # You can track previous stages
    preprocessing_stage: str = "/path/to/preprocessing/run"

def core_logic(cfg: TrainConfig):
    """
    This is your pure, testable application logic.
    It takes a config and saves its results to the `save_dir`.
    """
    print(f"Running training with lr: {cfg.learning_rate}")
    print(f"Using dataset: {cfg.dataset_path}")
    
    # Your ML code here...
    # For this example, we'll just create a dummy model file.
    save_dir = Path(cfg.save_dir)
    (save_dir / "model.pt").touch()
    
    print(f"Model saved in: {save_dir}")
    return cfg # Return the final, resolved config
```

**2. Create an entry point script (`main.py`) to orchestrate the run:**

```python
# main.py
import naga
from my_project.main import core_logic, TrainConfig

# Use @naga.clicfg to handle configuration from CLI or Python
@naga.clicfg(config_class=TrainConfig)
def main(cfg):
    """
    This entry point orchestrates the experiment by combining the
    core logic with Naga's MLOps tools.
    """
    # Use the mlflow_lock context manager to manage the MLflow run
    with naga.mlflow_lock(path=cfg.save_dir):
        
        # --- 1. Execute the Core Logic ---
        final_cfg = core_logic(cfg)

        # --- 2. Create the Runlock ---
        # This creates the definitive receipt for the run after it has finished.
        if final_cfg:
            naga.runlock(
                config=final_cfg,
                # Create a new git commit to capture the exact state of the code
                repos={'main_repo': '.'}, 
                # Hash the dataset to track data provenance
                data={'raw_data': final_cfg.dataset_path},
                # Link this run to its predecessors
                prevs=[final_cfg.preprocessing_stage]
            )
            print(f"run.lock created at {final_cfg.save_dir}")

if __name__ == "__main__":
    main()
```

**3. Run from the command line:**

```bash
# Run with default configuration
pixi run python main.py

# Override parameters from the CLI
pixi run python main.py -o learning_rate=0.005 dataset_path=data/v2/iris.csv
```

This workflow gives you a clear, explicit, and reproducible structure for your experiments.