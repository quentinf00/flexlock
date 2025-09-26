"""Configuration decorator for Naga."""
import argparse
from omegaconf import OmegaConf, open_dict, DictConfig
import sys
import inspect
from pathlib import Path
from .parallel import ParallelExecutor, load_tasks

def clicfg(fn):
    """
    A decorator that wraps a function to provide CLI configuration capabilities
    using OmegaConf. It allows specifying a base config, overrides, and an
    experiment key. It also adds support for parallel execution.
    """
    def wrapped(*args, **kwargs):
        print(args)
        parser = argparse.ArgumentParser(description="CLI configuration for a Naga function.")
        # Standard config arguments
        parser.add_argument('--config', default=None, help="Path to the base YAML configuration file.")
        parser.add_argument('--experiment', default=None, help="Dot-separated key to select a specific experiment from the config.")
        parser.add_argument('--overrides_path', default=None, help="Path to a YAML file with configuration overrides.")
        parser.add_argument('-o', '--overrides_dot', nargs='*', default=None, help="Dot-separated key-value pairs for overrides (e.g., 'param=10').")

        # Parallel execution arguments
        parser.add_argument('--tasks', default=None, help="Path to a file with a list of tasks (e.g., .txt, .yaml).")
        parser.add_argument('--tasks-key', default=None, help="Dot-separated key to select a list of tasks from the config.")
        parser.add_argument('--task-to', default=None, help="Dot-separated key where to merge the task in the config.")
        parser.add_argument('--n_jobs', type=int, default=1, help="Number of parallel jobs for joblib.")
        parser.add_argument('--slurm_config', default=None, help="Path to a Slurm configuration file for submitit.")

        if 'ipykernel_launcher' in sys.argv[0] or 'pytest' in sys.argv[0]:
            cli_args = parser.parse_args([])
        else:
            cli_args = parser.parse_args()

        # Start with a base config. If the wrapped function has a default, use it.
        # Otherwise, start with an empty config.
        cfg = OmegaConf.create()
        signature = inspect.signature(fn)
        defaults = [
            v.default
            for k, v in signature.parameters.items()
            if v.default is not inspect.Parameter.empty
        ]
        print(f"{defaults=}")
        def isconfig(x):
            try: 
                c = OmegaConf.create(x)
                return isinstance(c, DictConfig)
            except:
                return False
            
        default_cfg = next((arg for arg in defaults if isconfig(arg)), None)
        if default_cfg:
            cfg = default_cfg.copy()

        with open_dict(cfg):
            if cli_args.config:
                cfg.merge_with(OmegaConf.load(cli_args.config))
            if cli_args.overrides_path:
                cfg.merge_with(OmegaConf.load(cli_args.overrides_path))
            if cli_args.overrides_dot:
                cfg.merge_with(OmegaConf.from_dotlist(cli_args.overrides_dot))

        if cli_args.experiment:
            cfg = OmegaConf.select(cfg, cli_args.experiment)
        
        print(f"{cfg=}")
        if "save_dir" not in cfg:
            print("Warning: No save_dir found in config")
        else:
            save_dir = Path(cfg.save_dir)
            save_dir.mkdir(parents=True, exist_ok=True)
            OmegaConf.save(cfg, save_dir / 'config.yaml')

        # Parallel execution logic
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
                # The executor's run method will handle calling the original function `fn`
                # for each task, so we return its result.
                return executor.run()
            else:
                print("Warning: --tasks or --tasks-key provided, but no tasks were loaded. Running once.")

        # Default behavior: run the function once with the resolved config.
        print(args)
        args_cfg = OmegaConf.create(args[0])
        final_cfg = OmegaConf.merge(cfg, args_cfg)
        return fn(final_cfg, *args[1:], **kwargs)
    
    return wrapped
