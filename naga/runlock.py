"""State management decorator for Naga."""
from functools import wraps
from pathlib import Path
from omegaconf import OmegaConf, DictConfig
import yaml

from .context import run_context

def runlock(fn):
    """
    A decorator that manages the state of a run by creating a `run.lock` file.

    This decorator should be placed *before* the `@clicfg` decorator so it can
    access the final, resolved configuration object.

    It gathers information from the run context (like the git commit from `@snapshot`)
    and the configuration object, then saves it to `cfg.save_dir / 'run.lock'`.
    """
    @wraps(fn)
    def wrapped(cfg: DictConfig, *args, **kwargs):
        # Ensure the save directory exists
        save_dir = Path(cfg.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        # The main function logic is executed first
        result = fn(cfg, *args, **kwargs)

        # After the run, gather all information for the lock file
        run_data = {
            "config": OmegaConf.to_container(cfg, resolve=True),
            **run_context.get()
        }

        # Write the run.lock file
        lock_file_path = save_dir / "run.lock"
        with open(lock_file_path, "w") as f:
            yaml.dump(run_data, f, default_flow_style=False, sort_keys=False)

        return result
    return wrapped
