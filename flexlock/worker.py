"""Worker process for executing FlexLock tasks."""

import os
import time
from loguru import logger
from multiprocessing import Process
from .taskdb import claim_next_task, finish_task, pending_count
from flexlock.utils import merge_task_into_cfg
from flexlock.utils import instantiate
from flexlock.snapshot import snapshot
from pathlib import Path
from omegaconf import OmegaConf, open_dict


def _extract_tracking_info(cfg):
    """
    Extract tracking info from config for task snapshots.
    """
    data = {}
    prevs = []

    # Check if the node has tracking instructions
    if "_snapshot_" in cfg:
        snap_cfg = cfg._snapshot_
        
        if "data" in snap_cfg:
            data.update(OmegaConf.to_container(snap_cfg.data, resolve=True))

        # Explicit lineage paths (files we want to link but not hash)
        if "prevs" in snap_cfg:
            p = OmegaConf.to_container(snap_cfg.prevs, resolve=True)
            if isinstance(p, list):
                prevs.extend(p)
            else:
                prevs.append(p)

    # "prevs_from_data": Automatically treat hashed data paths as lineage candidates
    # This matches the logic: if we use a file, check if it came from a FlexLock run
    prevs.extend(data.values())

    return data, prevs


def worker_loop(func, cfg, task_to: str, db_path):
    """A worker loop that continuously claims and executes tasks from the task database."""
    if func is None:
        func = instantiate
    node = os.getenv("HOSTNAME") or "local"
    
    # Find the master lock file (parent lock)
    # The master lock should be in the parent directory of the db_path
    db_dir = Path(db_path).parent
    master_lock = db_dir / "run.lock"
    
    while True:
        task = claim_next_task(db_path, node)
        if task is None:
            if pending_count(db_path) == 0:
                logger.info("All tasks finished.")
                break
            logger.debug("No task available – sleeping 5s")
            time.sleep(5)
            continue

        logger.info(f"Worker {node} running task {task}")
        try:
            task_cfg = merge_task_into_cfg(cfg, task, task_to)
            
            # 3. Resolve Data Dependencies (Just-in-Time)
            # We re-run resolution because task overrides might change data paths
            # e.g. override="data.fold=1" changes ${input:data/fold_${data.fold}}
            data, prevs = _extract_tracking_info(task_cfg)
            
            # 4. Create DELTA Snapshot
            # We pass the path to the Master Lock
            task_save_dir = Path(task_cfg.get("save_dir", db_dir / f"task_{task.get('task_id', 'unknown')}"))
            task_save_dir.mkdir(parents=True, exist_ok=True)
            
            snapshot(
                task_cfg,
                data=data, # Capture task-specific data
                prevs=prevs,
                repos=None, # Skip repos, we rely on Parent
                parent_lock=str(master_lock) if master_lock.exists() else None,
                save_path=task_save_dir / "run.lock"
            )
            
            # 5. Execute
            result = func(task_cfg)
            logger.info(f"Task successful: {task_cfg}")
            finish_task(db_path, task, result=result)
        except Exception as e:
            logger.error(f"Task failed: {e}", exc_info=True)
            finish_task(db_path, task, error=str(e))
