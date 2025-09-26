# The Naga Philosophy: Guiding Principles

Naga is a lightweight library designed to bring clarity, reproducibility, and scalability to your computational experiments. It is built on a "Don't Repeat Yourself" (DRY) philosophy, using decorators to handle the boilerplate of experiment tracking so you can focus purely on your core logic.

Adhering to the following principles will help you get the most out of Naga and ensure your projects are robust and easy to manage.

## 1. Configuration is King

Your code should be independent of specific parameters. All configuration—from learning rates and model sizes to file paths and feature flags—should live outside your Python scripts, primarily in YAML files.

- **DO:** Define your configuration structure with a `dataclass` and use it to create a default. Your main function should accept a single `OmegaConf` object and return it after its work is done.

  ```python
  # main.py
  from naga import clicfg, mlflow_log_run
  from omegaconf import OmegaConf
  from dataclasses import dataclass

  @dataclass
  class TrainConfig:
      learning_rate: float = 0.01
      data_path: str = "/path/to/default/data"
      # A unique save_dir is critical for logging and tracking.
      # It can be set via config files or CLI overrides.
      save_dir: str = "/tmp/naga/runs/${now:%Y-%m-%d_%H-%M-%S}"

  @clicfg
  def train(cfg: TrainConfig = OmegaConf.structured(TrainConfig)):
      """
      Runs the experiment and saves artifacts to cfg.save_dir.
      Returns the resolved config.
      """
      print(f"Learning rate: {cfg.learning_rate}")
      print(f"Saving artifacts to: {cfg.save_dir}")
      # ... your logic here ...
      # e.g., Path(cfg.save_dir).mkdir(parents=True, exist_ok=True)
      #        (Path(cfg.save_dir) / "model.pt").touch()
      return cfg
  
  if __name__ == "__main__":
      # The train function is now complete.
      # We can pass its result to another function for post-processing.
      final_cfg = train()
      # log_results(final_cfg) # See section 4
  ```

- **DON'T:** Hardcode paths, hyperparameters, or any other variables inside your functions.

## 2. Version Everything, Automatically

A result is meaningless if you cannot trace it back to the exact code and data that produced it. Naga's decorators are designed to make this effortless.

- **`@snapshot`**: Automatically records the Git commit hash of your source code.
- **`@track_data`**: Automatically computes and records a unique hash ("fingerprint") of your datasets.

## 3. The Atomic Run and the `run.lock`

Every single execution of your script should be treated as an **atomic unit**. The goal is to produce a `run.lock` file in the `save_dir` for each run. This file acts as the definitive "receipt" or "DNA" of that experiment, containing:
- The exact configuration used.
- The source code's Git commit hash.
- The unique hashes of all tracked data assets.

## 4. Separate Computation from Post-Processing

Your core computation function should have one job: run the experiment and save the results to disk. It should not be responsible for logging to external services.

- **DO:** Pass the final config from your experiment to a second, decorated function that handles logging. The `@mlflow_log_run` decorator automates this entire process.

  ```python
  # main.py (continued from above)

  @mlflow_log_run()
  def log_results(cfg: TrainConfig):
      """
      This function's body can be empty or contain custom MLflow logging.
      The decorator handles the rest.
      """
      print(f"Logging results from run located at: {cfg.save_dir}")
      # You can add custom logic here, like logging a specific figure:
      # if (Path(cfg.save_dir) / "roc_curve.png").exists():
      #     mlflow.log_artifact(Path(cfg.save_dir) / "roc_curve.png")
      pass

  if __name__ == "__main__":
      # 1. Run the experiment
      final_cfg = train()
      
      # 2. Log the results
      if final_cfg: # train() might return None in a parallel setup
          log_results(final_cfg)
  ```
The `@mlflow_log_run` decorator will automatically:
1.  Start an MLflow run.
2.  Find the `run.lock` file inside the `cfg.save_dir`.
3.  Parse the `config` section of the `run.lock` and log all key-value pairs as MLflow parameters.
4.  Find the `experiment.log` file (if it exists) and upload it as an artifact.
5.  Handle MLflow run resumption and linking, so re-logging the same `save_dir` updates the previous MLflow entry.

This pattern keeps your code clean, testable, and focused.

## 5. Design for a Single Run, Then Scale Effortlessly

The parallel execution features are a thin layer on top of a well-defined single run.

- **Key Requirement:** Your configuration **must** contain a `save_dir`. Naga relies on this path being unique for each task to track its completion status via a `.naga_done` folder.

- **Workflow:**
  1.  **Perfect Your Single Run:** Ensure your `train` and `log_results` flow works for one execution.
  2.  **Create a Task File:** List the items you want to iterate over in a `tasks.yaml`.
  3.  **Execute in Parallel:** Use the CLI arguments to scale up.

      ```bash
      # Run all tasks on a Slurm cluster
      pixi run python main.py --tasks tasks.yaml --task-to 'experiment' --slurm_config slurm.yaml
      ```
      When running in parallel, you can run a separate script later to scan all output directories and call `log_results` on each one, logging all your experiments in batch.