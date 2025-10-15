"""Configuration decorator for FlexLock."""

import argparse
from dataclasses import is_dataclass
from omegaconf import OmegaConf, DictConfig
import sys
from pathlib import Path
from .parallel import ParallelExecutor, load_tasks
from .debug import debug_on_fail
from .utils import to_dictconfig
from .resolvers import resolver_context


def flexcli(default_config=None, description=None, debug=None):
    """
    A decorator that wraps a function to provide CLI and programmatic configuration
    capabilities using OmegaConf.

    Args:
        default_config: The dataclass representing the configuration schema.
        description (str, optional): A description of the script to be displayed in the help message.
        debug: If True, enables debug mode with local variable injection on exceptions.
               If None (default), debug mode is determined by CLI args or FLEXLOCK_DEBUG env var.
    """

    def decorator(fn):
        def wrapper(**kwargs):
            # Use resolver context to ensure consistent resolver values within execution
            with resolver_context():
                    # --- Help Message Generation ---
                epilog_str = ""
                if default_config is not None:
                    default_cfg = to_dictconfig(default_config)
                    yaml_help = OmegaConf.to_yaml(default_cfg)
                    epilog_str = f"Default Configuration:\n---\n{yaml_help}"

                parser = argparse.ArgumentParser(
                    description=description,
                    epilog=epilog_str,
                    formatter_class=argparse.RawTextHelpFormatter,
                )

                # --- Argument Parsing ---
                # Standard config arguments
                parser.add_argument(
                    "--config",
                    default=None,
                    help="Path to the base YAML configuration file.",
                )
                parser.add_argument(
                    "--experiment",
                    default=None,
                    help="Dot-separated key to select a specific experiment from the config.",
                )
                parser.add_argument(
                    "--overrides_path",
                    default=None,
                    help="Path to a YAML file with configuration overrides.",
                )
                parser.add_argument(
                    "-o",
                    "--overrides_dot",
                    nargs="*",
                    default=[],
                    help="Dot-separated key-value pairs for overrides (e.g., 'param=10').",
                )

                # Parallel execution arguments
                parser.add_argument(
                    "--tasks",
                    default=None,
                    help="Path to a file with a list of tasks (e.g., .txt, .yaml).",
                )
                parser.add_argument(
                    "--tasks-key",
                    default=None,
                    help="Dot-separated key to select a list of tasks from the config.",
                )
                parser.add_argument(
                    "--task-to",
                    default=None,
                    help="Dot-separated key where to merge the task in the config.",
                )
                parser.add_argument(
                    "--n_jobs",
                    type=int,
                    default=1,
                    help="Number of parallel jobs for joblib.",
                )
                parser.add_argument(
                    "--slurm_config",
                    default=None,
                    help="Path to a Slurm configuration file for submitit.",
                )

                # Debug argument
                parser.add_argument(
                    "--debug",
                    action="store_true",
                    help="Enable debug mode with local variable injection on exceptions (overrides FLEXLOCK_DEBUG env var).",
                )

                # Logging arguments
                parser.add_argument(
                    "--verbose", action="store_true", help="Set log level to DEBUG."
                )
                parser.add_argument(
                    "--quiet",
                    action="store_true",
                    help="Keep console logger even when a logfile is specified.",
                )
                parser.add_argument(
                    "--logfile",
                    default=None,
                    help="Path to the log file. Defaults to 'save_dir/experiment.log'.",
                )

                # Determine if running from CLI or programmatically
                is_cli_call = (
                    len(sys.argv) > 1
                    and not any("ipykernel" in arg for arg in sys.argv)
                    and "pytest" not in sys.argv[0]
                )

                if is_cli_call:
                    cli_args = parser.parse_args()
                    dot_list_overrides = cli_args.overrides_dot
                else:
                    cli_args = parser.parse_args([])
                    dot_list_overrides = [f"{key}={value}" for key, value in kwargs.items()]

                # Determine debug mode: CLI arg > function param > environment variable
                if cli_args.debug:
                    debug_enabled = True
                elif debug is not None:  # Explicitly set to True or False
                    debug_enabled = debug
                else:
                    # Use environment variable as fallback
                    import os

                    debug_enabled = os.environ.get("FLEXLOCK_DEBUG", "false").lower() in (
                        "1",
                        "true",
                    )
                # --- Configuration Loading ---
                cfg = OmegaConf.create()
                if default_config is not None:
                    cfg = to_dictconfig(default_config)

                if cli_args.config:
                    cfg.merge_with(OmegaConf.load(cli_args.config))

                if cli_args.experiment:
                    cfg = OmegaConf.select(cfg, cli_args.experiment)
                    if not isinstance(cfg, DictConfig):
                        raise ValueError(
                            f"Experiment '{cli_args.experiment}' did not resolve to a dictionary in the config."
                        )

                if cli_args.overrides_path:
                    cfg.merge_with(OmegaConf.load(cli_args.overrides_path))

                if dot_list_overrides:
                    cfg.merge_with(OmegaConf.from_dotlist(dot_list_overrides))

                # --- Save Initial Config ---
                if "save_dir" in cfg:
                    save_dir = Path(cfg.save_dir)
                    save_dir.mkdir(parents=True, exist_ok=True)
                    OmegaConf.save(cfg, save_dir / "config.yaml")
                else:
                    print("Warning: No 'save_dir' found in the final configuration.")

                # --- Debug and Parallel Execution Logic ---
                # Debug mode and parallel execution are mutually exclusive
                if debug_enabled and (cli_args.tasks or cli_args.tasks_key):
                    print(
                        "Warning: Debug mode is enabled, parallel execution is disabled. Running tasks sequentially in debug mode."
                    )
                    # Run tasks sequentially in debug mode
                    tasks = load_tasks(cli_args.tasks, cli_args.tasks_key, cfg)
                    if tasks:
                        # Apply debug wrapper once
                        debug_fn = debug_on_fail(fn)
                        # Run each task individually with debug enabled
                        for task in tasks:
                            # Create a copy of cfg and merge the task
                            task_cfg = OmegaConf.merge(
                                cfg, OmegaConf.from_dotlist([f"{cli_args.task_to}={task}"])
                            )
                            debug_fn(task_cfg)
                        # For consistency of behavior, return None or a result
                        return None  # or could return some summary of the tasks run
                    else:
                        print(
                            "Warning: --tasks or --tasks-key provided, but no tasks were loaded. Running once."
                        )
                        # Apply debug wrapper and run once
                        debug_fn = debug_on_fail(fn)
                        return debug_fn(cfg)
                elif cli_args.tasks or cli_args.tasks_key:
                    # Parallel execution without debug
                    if not cli_args.task_to:
                        parser.error(
                            "--task-to is required when using --tasks or --tasks-key."
                        )

                    tasks = load_tasks(cli_args.tasks, cli_args.tasks_key, cfg)

                    if tasks:
                        executor = ParallelExecutor(
                            func=fn,
                            tasks=tasks,
                            task_to=cli_args.task_to,
                            cfg=cfg,
                            n_jobs=cli_args.n_jobs,
                            slurm_config=cli_args.slurm_config,
                        )
                        return executor.run()
                    else:
                        print(
                            "Warning: --tasks or --tasks-key provided, but no tasks were loaded. Running once."
                        )
                        # Even when no tasks are loaded, run the function normally without debug
                        return fn(cfg)
                else:
                        # Single run execution
                    if debug_enabled:
                        # Apply debug wrapper
                        wrapped_fn = debug_on_fail(fn)
                        return wrapped_fn(cfg)
                    else:
                        return fn(cfg)

        return wrapper

    return decorator
