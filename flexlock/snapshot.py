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
            self.data["repos"][name] = create_shadow_snapshot(path, ref_name=str(self.save_dir))

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

    def finalize(self, config):
        """
        Prepares the final snapshot dict but does not write it to disk.

        This allows callers to decide where to store the snapshot
        (file, DB, or both).

        Args:
            config: OmegaConf configuration object

        Returns:
            dict: Complete snapshot data structure
        """
        self.data["config"] = OmegaConf.to_container(config, resolve=True)
        return self.data

    def save(self, config):
        """
        Finalize and write to disk as run.lock.
        Now implemented by calling finalize() then writing.

        Returns:
            dict: The snapshot data that was written
        """
        snapshot_data = self.finalize(config)

        # Atomic Write
        self.save_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=self.save_dir, delete=False) as tf:
            yaml.dump(snapshot_data, tf, sort_keys=False)
            tmp_name = tf.name
        os.replace(tmp_name, self.save_dir / "run.lock")

        return snapshot_data


def snapshot(cfg, repos=None, data=None, prevs=None, parent_lock=None, save_path=None, return_snapshot=False):
    """
    Create a snapshot of the current run state.

    Args:
        cfg: OmegaConf configuration
        repos: Dict of repository paths to track
        data: Dict of data paths to hash
        prevs: List of paths to search for upstream lineage
        parent_lock: Path to parent run.lock (for delta snapshots)
        save_path: Custom save directory (overrides cfg.save_dir)
        return_snapshot: If True, return snapshot dict instead of/in addition to saving

    Returns:
        dict if return_snapshot=True, else None
    """
    if "save_dir" not in cfg:
        logger.warning("No save_dir specified in config; skipping snapshot.")
        return None if return_snapshot else None

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
        def _find_snapshot_dir(start_path: Path) -> tuple[Path, dict] | None:
            """
            Recursive search for FlexLock run metadata.

            Returns:
                tuple: (snapshot_dir, snapshot_data) or None

            Searches in order:
            1. .flexlock_marker file (points to DB)
            2. run.lock file (traditional file-based)
            3. Recursively up the directory tree
            """
            import json
            try:
                p = Path(start_path).resolve()
            except Exception:
                return None
            p = Path(start_path)
            if p.is_file():
                p = p.parent

            # Safety brake: stop at root or if path is invalid
            while p != p.parent:
                logger.debug(f"Checking for FlexLock metadata in: {p}")

                # Option 1: Check for marker file (DB-based snapshot)
                marker_file = p / ".flexlock_marker"
                if marker_file.exists():
                    try:
                        marker_data = json.loads(marker_file.read_text())
                        db_path = p / marker_data.get("db", "tasks.db")
                        task_id = marker_data.get("task_id")

                        if db_path.exists() and task_id:
                            from flexlock.taskdb import get_task_snapshot
                            snapshot_data = get_task_snapshot(db_path, task_id)
                            if snapshot_data:
                                logger.debug(f"Found DB-based snapshot via marker at: {p}")
                                return (p, snapshot_data)
                    except Exception as e:
                        logger.warning(f"Failed to read marker file at {marker_file}: {e}")

                # Option 2: Check for traditional run.lock file
                if (p / "run.lock").exists():
                    try:
                        with open(p / "run.lock") as f:
                            snapshot_data = yaml.safe_load(f)
                        logger.debug(f"Found file-based snapshot at: {p}")
                        return (p, snapshot_data)
                    except Exception as e:
                        logger.warning(f"Failed to read run.lock at {p}: {e}")

                p = p.parent

            return None

        for path_str in prevs:
            result = _find_snapshot_dir(path_str)

            if result:
                snapshot_dir, snapshot_data = result
                # We found an upstream FlexLock run!
                logger.debug(f"Found upstream FlexLock run at: {snapshot_dir}")
                try:
                    # Extract stage info from snapshot data
                    stage_info = {
                        "config": snapshot_data.get("config", {}),
                        "timestamp": snapshot_data.get("timestamp"),
                        "repos": snapshot_data.get("repos", {}),
                        "parent": snapshot_data.get("parent")
                    }

                    # Add to lineage
                    tracker.add_lineage(
                        name=snapshot_dir.name,  # e.g. "run_2023..." or "task_abc123"
                        path=str(snapshot_dir),
                        info=stage_info
                    )
                except Exception as e:
                    logger.warning(f"Found snapshot at {snapshot_dir} but failed to process: {e}")

    # 3. Save and/or return
    if return_snapshot:
        # For DB storage: return snapshot without writing file
        snapshot_data = tracker.finalize(cfg)
        return snapshot_data
    else:
        # Traditional behavior: write to file
        tracker.save(cfg)
        return None
