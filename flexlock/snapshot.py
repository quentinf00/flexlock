"""Snapshotting utilities for FlexLock."""

from datetime import datetime
from pathlib import Path
from omegaconf import OmegaConf
from .git_utils import create_shadow_snapshot
from .data_hash import hash_data
from .fingerprint import env_hashes
from .load_stage import load_stage_from_path
from .run_record import RunRecord, COMPLETE_MARKER, COMPLETE_VERSION
from loguru import logger
import uuid


def _source_scope(repos):
    """Effective configured scope, without claiming transitive import capture."""
    return {name: dict(path=str(Path(info['path']).resolve()),
                       include=list(info.get('include') or []),
                       exclude=list(info.get('exclude') or []))
            for name, info in (repos or {}).items()}


def write_complete_marker(save_dir: Path, result=None) -> Path:
    """Write run.complete atomically into ``save_dir``.

    Thin wrapper over :meth:`RunRecord.mark_complete` kept for backward
    compatibility. ``_find_matching_run`` requires both ``run.lock`` and
    ``run.complete`` for a cache hit.
    """
    return RunRecord(save_dir).mark_complete(result=result)


def record_code_drift(save_dir) -> dict:
    """Append ``code_drift`` to ``save_dir/run.lock`` if loaded code changed.

    Call when the run ends (success or failure). Compares the modules loaded
    in this process against the tree recorded in run.lock; see
    :func:`flexlock.git_utils.code_drift`. Never raises.
    """
    import yaml
    from .git_utils import code_drift

    try:
        lock = Path(save_dir) / "run.lock"
        with open(lock) as f:
            data = yaml.safe_load(f) or {}
        repos = data.get("repos")
        ts = data.get("timestamp")
        if not repos or not ts:
            return {}
        drift = code_drift(repos, datetime.fromisoformat(ts).timestamp())
        if drift:
            logger.warning(
                f"Code changed after the snapshot; the recorded tree may not "
                f"match what ran: {drift}"
            )
            data["code_drift"] = drift
            RunRecord(save_dir).write_lock(data)
        return drift
    except Exception as exc:
        logger.debug(f"code drift check failed for {save_dir}: {exc}")
        return {}


def is_complete(run_dir: Path) -> bool:
    """Return True if ``run_dir`` has both ``run.lock`` and ``run.complete``."""
    return RunRecord(run_dir).is_complete


class RunTracker:
    def __init__(self, save_dir, parent_lock=None, note=None):
        self.save_dir = Path(save_dir)
        self.parent_lock = Path(parent_lock) if parent_lock else None
        self.data = {"timestamp": datetime.now().astimezone().isoformat(),
                     "source_scope": {}}
        self._lineage_by_path = {}

        # Free-text intent recorded alongside run metadata (sibling of
        # timestamp/config). It never enters the fingerprint, so it can't
        # perturb caching or diffs.
        if note:
            self.data["note"] = str(note)

        if self.parent_lock:
            # We record the link, effectively saying "See parent for Git/Env"
            self.data["parent"] = str(self.parent_lock)

    def record_env(self, repos: dict):
        self.data['source_scope'] = _source_scope(repos)
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
                include=repo_info.get("include"),
                exclude=repo_info.get("exclude"),
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

        env = env_hashes(repos)
        if env:
            self.data["env"] = env

    def record_data(self, data_paths: dict):
        self.data["data"] = {k: hash_data(v) for k, v in data_paths.items()}
        self.data["data_identity"] = {
            k: dict(path=str(Path(v).resolve()),
                    method=("directory_selected_paths_and_content" if Path(v).is_dir()
                            else "file_content_with_mtime_cache"),
                    algorithm="xxh64")
            for k, v in data_paths.items()
        }

    def add_lineage(self, name: str, path: str, info: dict):
        """Add lineage information from upstream FlexLock runs."""
        from collections import Counter

        canonical = str(Path(path).resolve())
        label = self._lineage_by_path.get(canonical, (name, None))[0]
        self._lineage_by_path[canonical] = (label, info)
        counts = Counter(label for label, _ in self._lineage_by_path.values())
        lineage = {
            label if counts[label] == 1 else producer:
                {"path": producer, "info": details}
            for producer, (label, details) in self._lineage_by_path.items()
        }
        if len(lineage) != len(self._lineage_by_path):
            raise ValueError("Explicit lineage labels collide with producer paths")
        self.data["lineage"] = lineage

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
        # The captured reads/lineage have dedicated record fields. Do not nest
        # runtime capture buffers in each producer's config through long chains.
        snap = self.data["config"].get('_snapshot_', {})
        snap.pop('run_lock_reads', None)
        snap.pop('run_lock_records', None)
        return self.data

    def save(self, config):
        """
        Finalize and write to disk as run.lock.
        Now implemented by calling finalize() then writing.

        Returns:
            dict: The snapshot data that was written
        """
        snapshot_data = self.finalize(config)

        # Read the concrete save_dir from the finalized snapshot. save_dir is
        # baked to a string once at submit time (apply_save_dir_policy), so this
        # is just a lookup — no resolver fires here.
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
    meta=None,
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
        meta: Extra top-level keys for the record (e.g. a sweep master's
            ``task_record``). Never part of the fingerprint.

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
    if meta:
        tracker.data.update(meta)

    # 1. Record Git & Data (Hashing)
    if repos:
        tracker.record_env(repos)
    if data:
        logger.debug(f"Recording data for snapshot: {data}")
        tracker.record_data(data)

    # Known references are captured from the same producer read that supplied
    # callable arguments. Never re-read them here and substitute changed metadata.
    snap_cfg = cfg.get('_snapshot_', {})
    reads = snap_cfg.get('run_lock_reads', [])
    records = snap_cfg.get('run_lock_records', {})
    if OmegaConf.is_config(reads):
        reads = OmegaConf.to_container(reads, resolve=True)
    if OmegaConf.is_config(records):
        records = OmegaConf.to_container(records, resolve=True)
    evidence = []
    for path, info in records.items():
        tracker.add_lineage(Path(path).name, path, info)
    if reads:
        tracker.data['run_lock_reads'] = reads
        evidence.extend(dict(method='run_lock', path=entry['path'], field=entry['field'],
                             used_default=entry['used_default']) for entry in reads)
    explicit_prevs = {str(Path(path).resolve()) for path in snap_cfg.get('prevs', [])}
    for name, path in (data or {}).items():
        from .utils import _find_run_dir
        if snap_cfg.get('discover', {}).get('prevs', True):
            ancestor = _find_run_dir(path)
            if ancestor:
                evidence.append(dict(method='data_ancestor', path=str(Path(ancestor).resolve()),
                                     data=name, input_path=str(path)))
    for path in prevs or []:
        canonical = str(Path(path).resolve())
        if canonical in explicit_prevs or canonical not in {entry['path'] for entry in evidence}:
            evidence.append(dict(method='explicit', path=canonical))
    explicit_repos = snap_cfg.get('repos', {})
    evidence_repos = repos
    if evidence_repos is None and parent_lock:
        from .utils import extract_tracking_info
        evidence_repos, _, _ = extract_tracking_info(cfg)
    # A worker may inherit a larger campaign capture. Keep its own scope rather
    # than inheriting the master's union or rediscovering it when records are read.
    if repos is None and evidence_repos is not None:
        tracker.data['source_scope'] = _source_scope(evidence_repos)
    repo_evidence = {name: dict(path=str(Path(info['path'] if hasattr(info, 'get') else info).resolve()),
        method='explicit' if name in explicit_repos else 'target') for name, info in (evidence_repos or {}).items()}
    if evidence or repo_evidence:
        tracker.data['discovery'] = dict(repos=repo_evidence, lineage=evidence)

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

            from .record import load_record

            data = load_record(p)
            if data is not None:
                logger.debug(f"Found snapshot at: {p}")
                return (p, data)

            return None

        for path_str in prevs:
            if str(Path(path_str).resolve()) in records:
                continue
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
                    if 'source_scope' in snapshot_data:
                        stage_info['source_scope'] = snapshot_data['source_scope']

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
