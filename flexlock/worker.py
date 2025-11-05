# flexlock/worker.py
import os
import time
from loguru import logger
from multiprocessing import Process
from .taskdb import claim_next_task, finish_task, pending_count
from flexlock.utils import merge_task_into_cfg

def worker_loop(func, cfg, task_to: str, db_path):
    node = os.getenv("HOSTNAME") or "local"
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
            result = func(task_cfg)
            finish_task(db_path, task, result=result)
        except Exception as e:
            logger.error(f"Task failed: {e}", exc_info=True)
            finish_task(db_path, task, error=str(e))
