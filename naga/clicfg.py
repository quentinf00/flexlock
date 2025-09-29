"""Configuration decorator for Naga."""
import argparse
from omegaconf import OmegaConf, DictConfig
import sys
from pathlib import Path
from .parallel import ParallelExecutor, load_tasks

def clicfg(config_class=None, description=None):
    """
    A decorator that wraps a function to provide CLI and programmatic configuration
    capabilities using OmegaConf.
    
    Args:
        config_class: The dataclass representing the configuration schema.
        description (str, optional): A description of the script to be displayed in the help message.
    """

    def decorator(fn):
        def wrapper(**kwargs):
            # --- Help Message Generation ---
            epilog_str = ""
            if config_class:
                default_cfg = OmegaConf.structured(config_class)
                yaml_help = OmegaConf.to_yaml(default_cfg)
                epilog_str = f"Default Configuration:\n---\n{yaml_help}"

            parser = argparse.ArgumentParser(
                description=description,
                epilog=epilog_str,
                formatter_class=argparse.RawTextHelpFormatter
            )
            
            # --- Argument Parsing ---
            # Standard config arguments
            parser.add_argument('--config', default=None, help="Path to the base YAML configuration file.")
            parser.add_argument('--experiment', default=None, help="Dot-separated key to select a specific experiment from the config.")
            parser.add_argument('--overrides_path', default=None, help="Path to a YAML file with configuration overrides.")
            parser.add_argument('-o', '--overrides_dot', nargs='*', default=[], help="Dot-separated key-value pairs for overrides (e.g., 'param=10').")

            # Parallel execution arguments
            parser.add_argument('--tasks', default=None, help="Path to a file with a list of tasks (e.g., .txt, .yaml).")
            parser.add_argument('--tasks-key', default=None, help="Dot-separated key to select a list of tasks from the config.")
            parser.add_argument('--task-to', default=None, help="Dot-separated key where to merge the task in the config.")
            parser.add_argument('--n_jobs', type=int, default=1, help="Number of parallel jobs for joblib.")
            parser.add_argument('--slurm_config', default=None, help="Path to a Slurm configuration file for submitit.")

            # Determine if running from CLI or programmatically
            is_cli_call = len(sys.argv) > 1 and not any('ipykernel' in arg for arg in sys.argv) and 'pytest' not in sys.argv[0]

            if is_cli_call:
                cli_args = parser.parse_args()
                dot_list_overrides = cli_args.overrides_dot
            else:
                cli_args = parser.parse_args([])
                dot_list_overrides = [f"{key}={value}" for key, value in kwargs.items()]

            # --- Configuration Loading ---
            cfg = OmegaConf.structured(config_class) if config_class else OmegaConf.create()

            if cli_args.config:
                cfg.merge_with(OmegaConf.load(cli_args.config))

            if cli_args.experiment:
                cfg = OmegaConf.select(cfg, cli_args.experiment)
                if not isinstance(cfg, DictConfig):
                    raise ValueError(f"Experiment '{cli_args.experiment}' did not resolve to a dictionary in the config.")

            if cli_args.overrides_path:
                cfg.merge_with(OmegaConf.load(cli_args.overrides_path))

            if dot_list_overrides:
                cfg.merge_with(OmegaConf.from_dotlist(dot_list_overrides))

            # --- Save Initial Config ---
            if "save_dir" in cfg:
                save_dir = Path(cfg.save_dir)
                save_dir.mkdir(parents=True, exist_ok=True)
                OmegaConf.save(cfg, save_dir / 'config.yaml')
            else:
                print("Warning: No 'save_dir' found in the final configuration.")

            # --- Parallel Execution Logic ---
            if cli_args.tasks or cli_args.tasks_key:
                if not cli_args.task_to:
                    parser.error("--task-to is required when using --tasks or --tasks-key.")
                
                tasks = load_tasks(cli_args.tasks, cli_args.tasks_key, cfg)
                
                if tasks:
                    executor = ParallelExecutor(
                        func=fn,
                        tasks=tasks,
                        task_to=cli_args.task_to,
                        cfg=cfg,
                        n_jobs=cli_args.n_jobs,
                        slurm_config=cli_args.slurm_config
                    )
                    return executor.run()
                else:
                    print("Warning: --tasks or --tasks-key provided, but no tasks were loaded. Running once.")

            # --- Single Run Execution ---
            return fn(cfg)

        return wrapper
    return decorator
