"""Snapshotting utilities for FlexLock."""

import yaml
import tempfile
import os
from datetime import datetime
from pathlib import Path
from omegaconf import OmegaConf
from .git_utils import create_shadow_snapshot
from .data_hash import hash_data
from .load_stage import load_stage_from_path
from loguru import logger


class RunTracker:
    def __init__(self, save_dir, parent_lock=None):
        self.save_dir = Path(save_dir)
        self.parent_lock = Path(parent_lock) if parent_lock else None
        self.data = {"timestamp": datetime.now().isoformat()}
        
        if self.parent_lock:
            # We record the link, effectively saying "See parent for Git/Env"
            self.data["parent"] = str(self.parent_lock)

    def record_env(self, repos: dict):
        # Optimization: If we have a parent, we MIGHT skip recording git
        # IF we are sure code hasn't changed between main process and worker
        # (which is true for multiprocessing/slurm typically).
        if self.parent_lock:
            return
            
        self.data["repos"] = {}
        for name, path in repos.items():
            # Uses the Shadow Index logic
            self.data["repos"][name] = create_shadow_snapshot(path)

    def record_data(self, data_paths: dict):
        self.data["data"] = {k: hash_data(v) for k, v in data_paths.items()}

    def add_lineage(self, name: str, path: str, info: dict):
        """Add lineage information from upstream FlexLock runs."""
        if "lineage" not in self.data:
            self.data["lineage"] = {}
        
        self.data["lineage"][name] = {
            "path": path,
            "info": info
        }

    def save(self, config):
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.data["config"] = OmegaConf.to_container(config, resolve=True)

        # Atomic Write
        with tempfile.NamedTemporaryFile("w", dir=self.save_dir, delete=False) as tf:
            yaml.dump(self.data, tf, sort_keys=False)
            tmp_name = tf.name
        os.replace(tmp_name, self.save_dir / "run.lock")


def snapshot(cfg, repos=None, data=None, prevs=None, parent_lock=None, save_path=None):
    if "save_dir" not in cfg:
        logger.warning("No save_dir specified in config; skipping snapshot.")
        return
    
    # Use custom save_path if provided, otherwise use cfg.save_dir
    save_dir = Path(save_path) if save_path else Path(cfg.save_dir)
    
    tracker = RunTracker(save_dir, parent_lock=parent_lock)
    
    # 1. Record Git & Data (Hashing)
    if repos:
        tracker.record_env(repos)
    if data:
        logger.debug(f"Recording data for snapshot: {data}")
        tracker.record_data(data)

    # 2. Record Lineage (Automatic Discovery)
    if prevs:
        logger.debug(f"Looking for upstream FlexLock runs in: {prevs}")
        def _find_snapshot_dir(start_path: Path) -> Path | None:
            """Recursive search up the tree for run.lock"""
            try:
                p = Path(start_path).resolve()
            except Exception:
                return None
            p = Path(start_path) 
            if p.is_file():
                p = p.parent
            
            # Safety brake: stop at root or if path is invalid
            while p != p.parent:
                logger.debug(f"Checking for run.lock in: {p}")
                if (p / "run.lock").exists():
                    return p
                p = p.parent
            return None

        for path_str in prevs:
            snapshot_dir = _find_snapshot_dir(path_str)
            
            if snapshot_dir:
                # We found an upstream FlexLock run!
                logger.debug(f"Found upstream FlexLock run at: {snapshot_dir}")
                try:
                    stage_info = load_stage_from_path(str(snapshot_dir))
                    logger.debug(f"Loaded stage info: {stage_info}")
                    
                    # Add to lineage
                    tracker.add_lineage(
                        name=snapshot_dir.name,  # e.g. "run_2023..."
                        path=str(snapshot_dir),
                        info=stage_info
                    )
                except Exception as e:
                    logger.warning(f"Found run.lock at {snapshot_dir} but failed to load: {e}")

    tracker.save(cfg)
