"""Worker process for executing FlexLock tasks.

The worker is deliberately single-threaded while the user function runs: no
background heartbeat thread or process. A live background thread would turn
any fork the user's code performs (PyTorch DataLoader workers, DDP, ...) into
a multi-threaded fork and corrupt the CUDA runtime in the child
(``cudaErrorSystemNotReady`` / "Unexpected error from cudaGetDeviceCount()").
Liveness is instead reconciled by the controller against the OS/scheduler's
authoritative view of worker state (see ``ParallelExecutor``).
"""

import json
import os
import random
import time
import traceback
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger

from .taskdb import claim_next_tasks, finish_tasks, pending_count
from flexlock.utils import merge_task_into_cfg, instantiate, extract_tracking_info
from flexlock.resolvers import resolve_deferred
from flexlock.snapshot import snapshot
from flexlock.run_record import RunRecord
from flexlock.fingerprint import fingerprint as compute_fingerprint
from flexlock import index
from flexlock import config as _config
from flexlock.git_utils import code_drift


def _current_job_id() -> str | None:
    """Best-effort scheduler job id from the environment (SLURM/PBS)."""
    return (
        os.getenv("SLURM_JOB_ID")
        or os.getenv("PBS_JOBID")
        or None
    )


def _preflight_cuda() -> "tuple[bool, str]":
    """Check that a CUDA context can actually be created on this node.

    Returns ``(ok, detail)``. Enabling this (``FLEXLOCK_PREFLIGHT_CUDA=1``)
    asserts "this job needs a working GPU", so anything short of a successful
    allocation is a failure:

    - torch not importable -> skipped (``ok=True``); it's a misconfiguration,
      not a node fault, and the user function will report it plainly.
    - ``cuda.is_available()`` False, or a real allocation raises -> ``ok=False``.
      A bare ``torch.zeros(1, device='cuda')`` is exactly what fails with
      ``cudaErrorSystemNotReady`` (802) on a node whose GPU stack is unhealthy
      (Fabric Manager down, driver/kernel-module mismatch).
    - allocation succeeds -> ``ok=True``.
    """
    try:
        import torch
    except Exception as e:  # torch absent / broken install
        return True, f"skipped (torch not importable: {e})"

    try:
        if not torch.cuda.is_available():
            return False, "torch.cuda.is_available() is False (no usable GPU)"
        x = torch.zeros(1, device="cuda")
        torch.cuda.synchronize()
        del x
        return True, f"ok ({torch.cuda.get_device_name(0)})"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def worker_loop(func, cfg, task_to: str, db_path, tags=None):
    """Claim and execute tasks from the task database until none remain.

    ``tags`` restricts which rows this worker claims (and the idle-check
    pending count). ``None`` (default) claims any row, matching legacy
    untagged DBs and the ``flexlock-worker`` CLI without ``--tags``.
    """
    if func is None:
        func = instantiate
    node = os.getenv("HOSTNAME") or "local"
    job_id = _current_job_id()

    db_path = Path(db_path)
    db_dir = db_path.parent
    master_lock = db_dir / "run.lock"

    # Optional GPU pre-flight: fail fast on an unhealthy node before claiming
    # any task, so a bad GPU stack surfaces as one clear log line rather than
    # an opaque CUDA traceback deep inside the user's training. Tasks are left
    # pending for a healthy worker to pick up.
    if _config.PREFLIGHT_CUDA:
        ok, detail = _preflight_cuda()
        if not ok:
            logger.error(
                f"[preflight] CUDA unusable on node {node}: {detail}. "
                f"Not claiming any task — they stay pending for another worker. "
                f"This is almost always a node/driver problem (NVIDIA Fabric "
                f"Manager down or driver/kernel-module mismatch), not your code. "
                f"Resubmit excluding this node (e.g. sbatch --exclude={node})."
            )
            return
        logger.info(f"[preflight] CUDA {detail} on node {node}")

    # Stagger startup so multiple workers don't all claim the same task.
    time.sleep(random.uniform(0, 5))

    # Claiming several tasks per transaction (FLEXLOCK_CLAIM_BATCH) divides
    # the write-lock traffic on the shared DB by the batch size; per-task
    # outcomes are buffered and flushed in one transaction per batch. A worker
    # that dies mid-batch strands the unstarted claims as 'running' — the
    # controller's orphan reconcile (or --reclaim) recovers them, same as a
    # death mid-task today.
    claim_batch = max(1, _config.CLAIM_BATCH)

    while True:
        batch = claim_next_tasks(
            db_path, node, job_id, tags=tags, n=claim_batch
        )
        if not batch:
            if pending_count(db_path, tags=tags) == 0:
                logger.info("All tasks finished.")
                break
            logger.debug("No task available – sleeping 5s")
            time.sleep(5)
            continue

        finished: list[dict] = []
        try:
            for task in batch:
                _run_one_task(
                    func, cfg, task_to, db_path, db_dir, master_lock,
                    node, task, finished,
                )
        finally:
            finish_tasks(db_path, finished)


_master_cache: dict = {}


def _master_code(master_lock: Path):
    """``(repos, snapshot epoch)`` from the sweep master run.lock, read once."""
    key = str(master_lock)
    if key not in _master_cache:
        repos, since = {}, None
        try:
            with open(master_lock) as f:
                data = yaml.safe_load(f) or {}
            repos = data.get("repos") or {}
            ts = data.get("timestamp")
            since = datetime.fromisoformat(ts).timestamp() if ts else None
        except Exception as exc:
            logger.debug(f"Could not read master lock {master_lock}: {exc}")
        _master_cache[key] = (repos, since)
    return _master_cache[key]


def _task_code_drift(master_lock: Path) -> dict:
    """Loaded repo files that changed since the master snapshot (see code_drift)."""
    repos, since = _master_code(master_lock)
    if not repos or since is None:
        return {}
    try:
        return code_drift(repos, since)
    except Exception as exc:
        logger.debug(f"code drift check failed: {exc}")
        return {}


def _with_drift(snapshot_data, master_lock):
    """Return the task snapshot extended with ``code_drift``, or None if clean."""
    if not snapshot_data:
        return None
    drift = _task_code_drift(master_lock)
    if not drift:
        return None
    logger.warning(
        f"Code changed after the snapshot; the recorded tree may not match "
        f"what ran: {drift}"
    )
    return dict(snapshot_data, code_drift=drift)


def _run_one_task(
    func, cfg, task_to, db_path, db_dir, master_lock, node, task, finished
):
    """Execute one claimed task; append its outcome record to ``finished``.

    The record is written to the DB by the caller's per-batch
    ``finish_tasks`` flush (also on interrupt, via its ``finally``).
    """
    logger.info(f"Worker {node} running task {task}")

    from flexlock.taskdb import _hash_task
    task_id = _hash_task(task)

    task_save_dir = None
    snapshot_data = None
    try:
        task_cfg = merge_task_into_cfg(cfg, task, task_to)

        # Single deferred-resolution point: run_lock/latest fire exactly
        # once, here at stage start on the worker, now that the per-item
        # override has been merged in. Everything else was already frozen
        # to concrete values at submit time.
        task_cfg = resolve_deferred(task_cfg)

        repos, data, prevs = extract_tracking_info(task_cfg)

        task_save_dir = Path(task_cfg.get("save_dir", db_dir / f"task_{task_id}"))
        task_save_dir.mkdir(parents=True, exist_ok=True)

        # Compute the fingerprint with the task's full git identity (repos
        # from the merged config) so a task cache-hits when the same config
        # is later run serially. The run.lock snapshot itself still uses the
        # parent_lock delta optimisation (repos=None).
        try:
            task_fp = compute_fingerprint(task_cfg, repos=repos, data=data)
        except Exception as exc:
            logger.warning(f"Could not compute task fingerprint: {exc}")
            task_fp = None

        snapshot_data = snapshot(
            task_cfg,
            data=data,
            prevs=prevs,
            repos=None,
            parent_lock=str(master_lock) if master_lock.exists() else None,
            return_snapshot=True,
            fingerprint=task_fp,
        )

        if snapshot_data:
            from flexlock.taskdb import update_task_snapshot
            update_task_snapshot(db_path, task_id, snapshot_data)

        marker_file = task_save_dir / ".flexlock_marker"
        db_abs = db_path.resolve()
        try:
            db_str = str(db_abs.relative_to(task_save_dir.parent.resolve()))
        except ValueError:
            db_str = str(db_abs)
        marker_file.write_text(json.dumps({"db": db_str, "task_id": task_id}, indent=2))

        result = func(task_cfg)
        logger.info(f"Task successful: {task_cfg}")

        record = RunRecord(task_save_dir)
        try:
            record.write_results(result)
        except Exception as e:
            logger.warning(f"Could not write results.json at {task_save_dir}: {e}")

        record.mark_complete(result=result)
        # Record this sweep task in the project-wide index so it's a
        # first-class cache entry (issue 1).
        if task_fp:
            index.record_task(task_save_dir, db_path, task_id, task_fp)
        finished.append(dict(
            task=task, result=result,
            snapshot=_with_drift(snapshot_data, master_lock),
        ))

    except KeyboardInterrupt:
        # SIGINT — mark the in-flight task interrupted so it's distinct
        # from a genuine failure, then propagate so the worker exits.
        logger.warning(f"Worker interrupted while running task {task_id}")
        finished.append(dict(task=task, status="interrupted"))
        raise

    except Exception as e:
        tb = traceback.format_exc()
        logger.exception(f"Task failed: {e}")
        # Mirror the failure into the task dir as run.error so triage needs
        # no sqlite; taskdb keeps the traceback too. write_error never raises.
        if task_save_dir is not None:
            RunRecord(task_save_dir).write_error(e, task_id=task_id, node=node)
        finished.append(dict(
            task=task, error=tb,
            snapshot=_with_drift(snapshot_data, master_lock),
        ))
