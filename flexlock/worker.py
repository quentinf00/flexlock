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
from pathlib import Path

from loguru import logger
from omegaconf import OmegaConf, DictConfig

from .taskdb import claim_next_task, finish_task, pending_count
from flexlock.utils import merge_task_into_cfg, instantiate, extract_tracking_info
from flexlock.resolvers import resolve_deferred
from flexlock.snapshot import snapshot
from flexlock.run_record import RunRecord
from flexlock.fingerprint import fingerprint as compute_fingerprint
from flexlock import index
from flexlock import config as _config


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


def _is_composite(task) -> bool:
    """True when ``task`` is a composite pipeline task (``{"_stages_": [...]}``)."""
    return isinstance(task, (dict, DictConfig)) and "_stages_" in task


def _run_stage(func, stage_cfg, db_path, db_dir, master_lock, node, task_id,
               stage: "str | None" = None):
    """Execute one already-merged stage config; return ``(save_dir, result)``.

    This is the per-task body shared by plain tasks (called once, after the
    task override is merged into the base config) and composite pipeline tasks
    (called once per stage, on self-contained stage configs). It resolves
    deferred resolvers, snapshots against the master lock, writes the
    ``.flexlock_marker``, runs the user function, and records
    ``results.json`` / ``run.complete`` / the fingerprint index entry.

    On failure a ``run.error`` sidecar is written into the stage dir (when
    known) and the exception propagates to the caller, which owns the task-DB
    terminal state.
    """
    task_save_dir = None
    try:
        # Single deferred-resolution point: run_lock/latest fire exactly
        # once, here at stage start on the worker. Everything else was
        # already frozen to concrete values at submit time.
        stage_cfg = resolve_deferred(stage_cfg)

        repos, data, prevs = extract_tracking_info(stage_cfg)

        task_save_dir = Path(stage_cfg.get("save_dir", db_dir / f"task_{task_id}"))
        task_save_dir.mkdir(parents=True, exist_ok=True)

        # Compute the fingerprint with the task's full git identity (repos
        # from the merged config) so a task cache-hits when the same config
        # is later run serially. The run.lock snapshot itself still uses the
        # parent_lock delta optimisation (repos=None).
        try:
            task_fp = compute_fingerprint(stage_cfg, repos=repos, data=data)
        except Exception as exc:
            logger.warning(f"Could not compute task fingerprint: {exc}")
            task_fp = None

        snapshot_data = snapshot(
            stage_cfg,
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

        result = func(stage_cfg)
        logger.info(f"Task successful: {stage_cfg}")

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
        return task_save_dir, result

    except KeyboardInterrupt:
        raise
    except Exception as e:
        # Mirror the failure into the task dir as run.error so triage needs
        # no sqlite; taskdb keeps the traceback too. write_error never raises.
        if task_save_dir is not None:
            RunRecord(task_save_dir).write_error(
                e, task_id=task_id, node=node, stage=stage
            )
        raise


def _detach_stage_cfg(stage_raw) -> DictConfig:
    """Build a self-contained DictConfig for one composite-task stage."""
    if isinstance(stage_raw, DictConfig):
        stage_raw = OmegaConf.to_container(
            stage_raw, resolve=False, throw_on_missing=False
        )
    return OmegaConf.create(stage_raw)


def _run_composite(func, task, db_path, db_dir, master_lock, node, task_id):
    """Run a composite task's stages sequentially; own its terminal DB state.

    Stages are self-contained configs frozen at build time — the base config
    is never re-merged into them. On a stage failure the remaining stages are
    aborted and the task row is marked ``failed`` with the traceback prefixed
    by the failing stage. On success the row's result is the per-stage list
    ``[{"save_dir": ..., "result": ...}, ...]``.

    ``KeyboardInterrupt`` propagates to :func:`worker_loop`, which marks the
    row interrupted; completed stage dirs keep their ``run.complete`` so a
    reclaim with ``_skip_complete_`` resumes past them.
    """
    stages = task["_stages_"]
    skip_complete = bool(task.get("_skip_complete_", False))
    n = len(stages)
    stage_results = []

    for i, stage_raw in enumerate(stages):
        stage_cfg = _detach_stage_cfg(stage_raw)
        save_dir = stage_cfg.get("save_dir")
        stage_name = Path(save_dir).name if save_dir else f"stage_{i}"
        label = f"stage {i + 1}/{n} {stage_name}"

        if (
            skip_complete
            and save_dir is not None
            and (Path(save_dir) / "run.complete").exists()
        ):
            logger.info(f"[{label}] {save_dir} already complete — skipping")
            stage_results.append(
                {
                    "save_dir": str(save_dir),
                    "result": RunRecord(save_dir).load_results(),
                    "skipped": True,
                }
            )
            continue

        logger.info(f"[{label}] running → {save_dir}")
        try:
            stage_dir, result = _run_stage(
                func, stage_cfg, db_path, db_dir, master_lock, node, task_id,
                stage=label,
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            tb = traceback.format_exc()
            logger.exception(f"[{label}] failed: {e} — aborting remaining stages")
            finish_task(db_path, task, error=f"[{label}] {tb}")
            return

        stage_results.append({"save_dir": str(stage_dir), "result": result})

    finish_task(db_path, task, result=stage_results)


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

    while True:
        task = claim_next_task(db_path, node, job_id, tags=tags)
        if task is None:
            if pending_count(db_path, tags=tags) == 0:
                logger.info("All tasks finished.")
                break
            logger.debug("No task available – sleeping 5s")
            time.sleep(5)
            continue

        logger.info(f"Worker {node} running task {task}")

        from flexlock.taskdb import _hash_task
        task_id = _hash_task(task)

        try:
            if _is_composite(task):
                # Composite pipeline task: self-contained stage configs run
                # sequentially; _run_composite owns the row's terminal state
                # (per-stage result list, or stage-labelled error).
                _run_composite(
                    func, task, db_path, db_dir, master_lock, node, task_id
                )
            else:
                task_cfg = merge_task_into_cfg(cfg, task, task_to)
                _, result = _run_stage(
                    func, task_cfg, db_path, db_dir, master_lock, node, task_id
                )
                finish_task(db_path, task, result=result)

        except KeyboardInterrupt:
            # SIGINT — mark the in-flight task interrupted so it's distinct
            # from a genuine failure, then propagate so the worker exits.
            logger.warning(f"Worker interrupted while running task {task_id}")
            finish_task(db_path, task, status="interrupted")
            raise

        except Exception as e:
            tb = traceback.format_exc()
            logger.exception(f"Task failed: {e}")
            finish_task(db_path, task, error=tb)
