"""Diff utilities for FlexLock."""

from omegaconf import OmegaConf


class RunDiff:
    def __init__(self, current, target):
        self.current = current
        self.target = target
        self.diffs = {}

    def compare_git(self):
        diff = []
        c_repos = self.current.get("repos", {})
        t_repos = self.target.get("repos", {})

        for name, c_info in c_repos.items():
            t_info = t_repos.get(name)
            if not t_info:
                diff.append(f"Repo {name} missing")
                continue

            # The Magic: Compare Tree Hashes (Content Identity)
            if c_info.get("tree") != t_info.get("tree"):
                 diff.append(f"Repo {name}: Content changed")

        if diff: self.diffs["git"] = diff
        return len(diff) == 0

    def compare_config(self):
        """Compare configurations, ignoring save_dir and timestamps."""
        c_config = self.current.get("config", {})
        t_config = self.target.get("config", {})
        
        # Create copies to avoid modifying original data
        c_config_copy = OmegaConf.to_container(OmegaConf.create(c_config))
        t_config_copy = OmegaConf.to_container(OmegaConf.create(t_config))
        
        # Remove or normalize fields that should not be compared
        def remove_ignored_fields(config):
            if isinstance(config, dict):
                # Remove save_dir and timestamp-related fields
                config.pop("save_dir", None)
                config.pop("timestamp", None)
                # Remove any timestamp-like keys (e.g., datetime fields)
                keys_to_remove = [k for k in config.keys() if k in ["timestamp", "date", "time", "datetime"]]
                for k in keys_to_remove:
                    config.pop(k, None)
                # Recursively process nested dictionaries
                for k, v in config.items():
                    if isinstance(v, dict):
                        remove_ignored_fields(v)
            return config
        
        c_clean = remove_ignored_fields(c_config_copy)
        t_clean = remove_ignored_fields(t_config_copy)
        
        # Convert to string representation for comparison
        import json
        c_str = json.dumps(c_clean, sort_keys=True, default=str)
        t_str = json.dumps(t_clean, sort_keys=True, default=str)
        
        config_match = c_str == t_str
        if not config_match:
            self.diffs["config"] = ["Configuration differs"]
        
        return config_match

    def compare_data(self):
        """Compare data hashes."""
        c_data = self.current.get("data", {})
        t_data = self.target.get("data", {})
        
        data_match = c_data == t_data
        if not data_match:
            self.diffs["data"] = ["Data differs"]
        
        return data_match

    def is_match(self):
        """Check if the current run matches the target run."""
        return self.compare_git() and self.compare_config() and self.compare_data()