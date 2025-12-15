"""Snapshotting utilities for FlexLock."""

import yaml
import tempfile
import os
from datetime import datetime
from pathlib import Path
from omegaconf import OmegaConf
from .git_utils import create_shadow_snapshot
from .data_hash import hash_data


class RunTracker:
    def __init__(self, save_dir):
        self.save_dir = Path(save_dir)
        self.data = {"timestamp": datetime.now().isoformat()}

    def record_env(self, repos: dict):
        self.data["repos"] = {}
        for name, path in repos.items():
            # Uses the Shadow Index logic
            self.data["repos"][name] = create_shadow_snapshot(path)

    def record_data(self, data_paths: dict):
        self.data["data"] = {k: hash_data(v) for k, v in data_paths.items()}

    def save(self, config):
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.data["config"] = OmegaConf.to_container(config, resolve=True)

        # Atomic Write
        with tempfile.NamedTemporaryFile("w", dir=self.save_dir, delete=False) as tf:
            yaml.dump(self.data, tf, sort_keys=False)
            tmp_name = tf.name
        os.replace(tmp_name, self.save_dir / "run.lock")


def snapshot(cfg, repos=None, data=None):
    if "save_dir" not in cfg: return
    tracker = RunTracker(cfg.save_dir)
    if repos: tracker.record_env(repos)
    if data: tracker.record_data(data)
    tracker.save(cfg)
