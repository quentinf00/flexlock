"""Configuration decorator for FlexLock."""

import argparse
from omegaconf import OmegaConf, DictConfig
import sys
from pathlib import Path
from .parallel import ParallelExecutor, load_tasks
from .debug import debug_on_fail
from .utils import to_dictconfig, merge_task_into_cfg
from loguru import logger


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
        def wrapper(cfg=None, **kwargs):
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
                help="Number of parallel jobs.",
            )
            parser.add_argument(
                "--slurm_config",
                default=None,
                help="Path to a Slurm configuration file.",
            )
            parser.add_argument(
                "--pbs_config",
                default=None,
                help="Path to a PBS configuration file.",
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
            if cfg is None:
                cfg = OmegaConf.create()
            else:
                cfg = to_dictconfig(cfg)
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

            # --- Resolve save_dir to ensure consistent directory across all tasks ---
            # Resolve the entire config to get the final save_dir, but then extract
            # it and merge it back to the unresolved config to keep other values unresolved
            if "save_dir" in cfg:
                # Create a temporary fully resolved config to get the resolved save_dir

                resolved_cfg = cfg.copy()
                OmegaConf.resolve(resolved_cfg)
                resolved_save_dir = resolved_cfg.save_dir
                save_dir = Path(resolved_save_dir)
                save_dir.mkdir(parents=True, exist_ok=True)
                OmegaConf.save(cfg, save_dir / "config.yaml")
                # Update the original config with the resolved save_dir
                cfg.save_dir = resolved_save_dir

            else:
                logger.info("Warning: No 'save_dir' found in the final configuration.")

            main_fn = debug_on_fail(fn, stack_depth=2) if debug_enabled else fn
            # --- Execution Logic ---
            # 1. Handle single run case first
            if not cli_args.tasks and not cli_args.tasks_key:
                return main_fn(cfg)

            # 2. Load tasks for batch execution
            tasks = load_tasks(cli_args.tasks, cli_args.tasks_key, cfg)
            logger.info(f"{len(tasks)} tasks loaded")

            if not tasks:
                logger.warning(
                    "--tasks or --tasks-key provided, but no tasks were loaded. Running once."
                )
                return main_fn(cfg)

            if not cli_args.task_to:
                parser.error("--task-to is required when using --tasks or --tasks-key.")

            # 3. Handle debug sequential run
            if debug_enabled:
                logger.warning(
                    "Debug mode is enabled, parallel execution is disabled. Running tasks sequentially."
                )
                for task in tasks:
                    task_cfg = merge_task_into_cfg(cfg, task, cli_args.task_to)
                    main_fn(task_cfg)  #  debug wrapper
                return None

            # 4. Handle parallel execution
            executor = ParallelExecutor(
                func=main_fn,  # not debug wrapper
                tasks=tasks,
                task_to=cli_args.task_to,
                cfg=cfg,
                n_jobs=cli_args.n_jobs,
                slurm_config=cli_args.slurm_config,
                pbs_config=cli_args.pbs_config,
            )
            return executor.run()

        return wrapper

    return decorator
