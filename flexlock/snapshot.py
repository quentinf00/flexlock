"""Snapshotting utilities for FlexLock."""

from datetime import datetime
from pathlib import Path
from omegaconf import OmegaConf
from .git_utils import create_shadow_snapshot
from .data_hash import hash_data
from .load_stage import load_stage_from_path
from .run_record import RunRecord, COMPLETE_MARKER, COMPLETE_VERSION
from loguru import logger
import uuid


def write_complete_marker(save_dir: Path, result=None) -> Path:
    """Write run.complete atomically into ``save_dir``.

    Thin wrapper over :meth:`RunRecord.mark_complete` kept for backward
    compatibility. ``_find_matching_run`` requires both ``run.lock`` and
    ``run.complete`` for a cache hit.
    """
    return RunRecord(save_dir).mark_complete(result=result)


def is_complete(run_dir: Path) -> bool:
    """Return True if ``run_dir`` has both ``run.lock`` and ``run.complete``."""
    return RunRecord(run_dir).is_complete


class RunTracker:
    def __init__(self, save_dir, parent_lock=None, note=None):
        self.save_dir = Path(save_dir)
        self.parent_lock = Path(parent_lock) if parent_lock else None
        self.data = {"timestamp": datetime.now().isoformat()}

        # Free-text intent recorded alongside run metadata (sibling of
        # timestamp/config). It never enters the fingerprint, so it can't
        # perturb caching or diffs.
        if note:
            self.data["note"] = str(note)

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
        for name, repo_info in repos.items():
            path = repo_info["path"]
            snapshot_data = create_shadow_snapshot(
                path,
                ref_name=str(self.save_dir) + f"_{uuid.uuid1().hex}",
            )
            # Store metadata for comparison-time filtering
            if repo_info.get("include"):
                snapshot_data["include"] = repo_info["include"]
            if repo_info.get("exclude"):
                snapshot_data["exclude"] = repo_info["exclude"]
            if repo_info.get("module"):
                snapshot_data["module"] = repo_info["module"]
            snapshot_data["path"] = path
            self.data["repos"][name] = snapshot_data

    def record_data(self, data_paths: dict):
        self.data["data"] = {k: hash_data(v) for k, v in data_paths.items()}

    def add_lineage(self, name: str, path: str, info: dict):
        """Add lineage information from upstream FlexLock runs."""
        if "lineage" not in self.data:
            self.data["lineage"] = {}

        self.data["lineage"][name] = {"path": path, "info": info}

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

        # Resolve save_dir in case it's a resolver (like ${vinc:})
        # We do this by accessing it from the finalized config in the snapshot
        resolved_save_dir = Path(
            snapshot_data["config"].get("save_dir", str(self.save_dir))
        )

        # Single on-disk-contract owner performs the atomic write.
        RunRecord(resolved_save_dir).write_lock(snapshot_data)

        # Remember the resolved dir so mark_complete can write next to run.lock
        self._resolved_save_dir = resolved_save_dir

        return snapshot_data

    def mark_complete(self, result=None) -> Path:
        """Write ``run.complete`` next to the previously-written ``run.lock``.

        Call this only after the user function returns successfully. The
        ``_find_matching_run`` cache check requires both files; an
        interrupted run leaves ``run.lock`` without ``run.complete`` and is
        correctly skipped instead of being treated as a stale cache hit.
        """
        target = getattr(self, "_resolved_save_dir", self.save_dir)
        return RunRecord(target).mark_complete(result=result)


def snapshot(
    cfg,
    repos=None,
    data=None,
    prevs=None,
    parent_lock=None,
    save_path=None,
    return_snapshot=False,
    fingerprint=None,
    note=None,
):
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
        return None

    # Use custom save_path if provided, otherwise use cfg.save_dir
    save_dir = Path(save_path) if save_path else Path(cfg.save_dir)

    tracker = RunTracker(save_dir, parent_lock=parent_lock, note=note)

    # Store the precomputed fingerprint (index key) so run.lock/DB snapshots
    # carry it and `flexlock reindex` can rebuild the index from disk.
    if fingerprint is not None:
        tracker.data["fingerprint"] = fingerprint

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
            Find run.lock at or directly in start_path.

            Returns:
                tuple: (snapshot_dir, snapshot_data) or None
            """
            try:
                p = Path(start_path).resolve()
            except Exception:
                return None
            if p.is_file():
                p = p.parent

            lock_file = p / "run.lock"
            if lock_file.exists():
                try:
                    data = OmegaConf.to_container(
                        OmegaConf.load(lock_file), resolve=True
                    )
                    logger.debug(f"Found snapshot at: {p}")
                    return (p, data)
                except Exception as e:
                    logger.warning(f"Failed to read run.lock at {p}: {e}")

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
                        "parent": snapshot_data.get("parent"),
                    }

                    # Add to lineage
                    tracker.add_lineage(
                        name=snapshot_dir.name,  # e.g. "run_2023..." or "task_abc123"
                        path=str(snapshot_dir),
                        info=stage_info,
                    )
                except Exception as e:
                    logger.warning(
                        f"Found snapshot at {snapshot_dir} but failed to process: {e}"
                    )

    # 3. Save and/or return
    if return_snapshot:
        # For DB storage: return snapshot without writing file
        snapshot_data = tracker.finalize(cfg)
        return snapshot_data
    else:
        # Traditional behavior: write to file
        tracker.save(cfg)
        return None
