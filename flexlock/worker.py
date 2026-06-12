"""Worker process for executing FlexLock tasks."""

import os
import random
import time
import traceback
from loguru import logger
from multiprocessing import Process
from .taskdb import claim_next_task, finish_task, pending_count
from flexlock.utils import merge_task_into_cfg, instantiate, extract_tracking_info
from flexlock.snapshot import snapshot, write_complete_marker
from pathlib import Path
from omegaconf import OmegaConf


def worker_loop(func, cfg, task_to: str, db_path):
    """A worker loop that continuously claims and executes tasks from the task database."""
    if func is None:
        func = instantiate
    node = os.getenv("HOSTNAME") or "local"

    # Find the master lock file (parent lock)
    # The master lock should be in the parent directory of the db_path
    db_dir = Path(db_path).parent
    master_lock = db_dir / "run.lock"

    time.sleep(random.uniform(0, 5))

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

        # Get task_id for DB operations
        from flexlock.taskdb import _hash_task

        task_id = _hash_task(task)

        try:
            task_cfg = merge_task_into_cfg(cfg, task, task_to)

            # 3. Resolve Data Dependencies (Just-in-Time)
            # We re-run resolution because task overrides might change data paths
            # e.g. override="data.fold=1" changes ${input:data/fold_${data.fold}}
            _, data, prevs = extract_tracking_info(task_cfg)

            # 4. Create DELTA Snapshot (DB storage only)
            # We pass the path to the Master Lock
            task_save_dir = Path(task_cfg.get("save_dir", db_dir / f"task_{task_id}"))
            task_save_dir.mkdir(parents=True, exist_ok=True)

            # Get snapshot data without writing file
            snapshot_data = snapshot(
                task_cfg,
                data=data,  # Capture task-specific data
                prevs=prevs,
                repos=None,  # Skip repos, we rely on Parent
                parent_lock=str(master_lock) if master_lock.exists() else None,
                return_snapshot=True,  # Return data for DB storage instead of writing file
            )

            # Store snapshot in database
            if snapshot_data:
                from flexlock.taskdb import update_task_snapshot

                update_task_snapshot(db_path, task_id, snapshot_data)
                logger.debug(f"Stored snapshot for task {task_id} in database")

            # Write marker file for lineage discovery. Prefer a path
            # relative to the task's parent dir (keeps the marker portable
            # if the sweep tree is moved together) but fall back to the
            # absolute path if the DB lives outside the task tree.
            import json

            marker_file = task_save_dir / ".flexlock_marker"
            db_abs = Path(db_path).resolve()
            try:
                db_str = str(db_abs.relative_to(task_save_dir.parent.resolve()))
            except ValueError:
                db_str = str(db_abs)
            marker_data = {"db": db_str, "task_id": task_id}
            marker_file.write_text(json.dumps(marker_data, indent=2))
            logger.debug(f"Wrote marker file at {marker_file}")

            # 5. Execute
            result = func(task_cfg)
            logger.info(f"Task successful: {task_cfg}")

            # Persist the function's return value as results.json so the
            # parent (api.submit) can rehydrate `ExecutionResult.result`.
            # Without this, parallel sweeps and isolated runs always come
            # back with result=None.
            try:
                results_file = task_save_dir / "results.json"
                payload = result if isinstance(result, dict) else {"result": result}
                results_file.write_text(json.dumps(payload, indent=2, default=str))
            except Exception as e:
                logger.warning(f"Could not write results.json at {task_save_dir}: {e}")

            write_complete_marker(task_save_dir, result=result)
            finish_task(db_path, task, result=result)
        except Exception as e:
            tb = traceback.format_exc()
            logger.exception(f"Task failed: {e}")
            finish_task(db_path, task, error=tb)
