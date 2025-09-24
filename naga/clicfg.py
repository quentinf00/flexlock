"""Configuration decorator for Naga."""
import argparse
from omegaconf import OmegaConf, open_dict, DictConfig
import sys

def clicfg(fn):
    """
    A decorator that wraps a function to provide CLI configuration capabilities
    using OmegaConf. It allows specifying a base config, overrides, and an
    experiment key.
    """
    def wrapped(*args, **kwargs):
        parser = argparse.ArgumentParser(description="CLI configuration for a Naga function.")
        # ... (rest of the parser setup is the same)
        parser.add_argument('--config', default=None, help="Path to the base YAML configuration file.")
        parser.add_argument('--experiment', default=None, help="Dot-separated key to select a specific experiment from the config.")
        parser.add_argument('--overrides_path', default=None, help="Path to a YAML file with configuration overrides.")
        parser.add_argument('-o', '--overrides_dot', nargs='*', default=None, help="Dot-separated key-value pairs for overrides (e.g., 'param=10').")

        args_list = [] if 'ipykernel_launcher' in sys.argv[0] else None
        cli_args = parser.parse_args(args_list)

        # Start with a base config. If the wrapped function has a default, use it.
        # Otherwise, start with an empty config.
        cfg = OmegaConf.create()
        if fn.__defaults__:
            default_cfg = next((arg for arg in fn.__defaults__ if isinstance(arg, DictConfig)), None)
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
        
        # Pass the generated cfg as the first argument, followed by others.
        return fn(cfg, *args[1:], **kwargs)
    
    return wrapped