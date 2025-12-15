"""Python API for FlexLock."""

from omegaconf import OmegaConf
from .runner import FlexLockRunner


class Project:
    def __init__(self, defaults: str):
        """
        Initialize a FlexLock project.
        
        Args:
            defaults: Python import path (e.g., pkg.config.defaults) containing the schema.
        """
        self.defaults = defaults
        self.runner = FlexLockRunner()

    def get(self, key: str):
        """
        Get a configuration by key from the defaults.
        
        Args:
            key: Dot-path to select a specific node from the config.
            
        Returns:
            The selected configuration.
        """
        # Load the full config and select the key
        args = ['--defaults', self.defaults, '--select', key]
        temp_runner = FlexLockRunner()
        
        # Parse only to get the selected config
        selected_config = temp_runner.load_config(
            temp_runner.parser.parse_args(args)
        )
        return OmegaConf.select(selected_config, key)

    def submit(self, config, sweep=None, n_jobs=1):
        """
        Submit a configuration for execution.
        
        Args:
            config: The configuration to execute.
            sweep: Optional list of task overrides for sweeping.
            n_jobs: Number of parallel workers (for sweeps).
            
        Returns:
            Results from execution.
        """
        # This is a simplified version - in real implementation, you might need
        # more sophisticated handling of the execution
        if sweep:
            # For sweep execution we would need to create a temporary runner
            # with appropriate parameters
            runner = FlexLockRunner()
            # This would require modifying the runner to accept a config directly
            # rather than parsing from command line arguments
            pass
        else:
            # For single execution, instantiate the config directly
            from flexlock.utils import instantiate
            return instantiate(config)