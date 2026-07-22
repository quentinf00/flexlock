"""Tests for the worker's optional CUDA pre-flight check."""

import sys
import types
from unittest.mock import patch

from flexlock.worker import _preflight_cuda, worker_loop


def _fake_torch(*, available=True, alloc_error=None, name="FakeGPU"):
    """Build a stand-in `torch` module exercising the cuda paths used by
    ``_preflight_cuda`` (is_available, zeros(device=), synchronize,
    get_device_name)."""
    torch = types.ModuleType("torch")

    def zeros(*a, **kw):
        if kw.get("device") == "cuda" and alloc_error is not None:
            raise alloc_error
        return object()

    cuda = types.SimpleNamespace(
        is_available=lambda: available,
        synchronize=lambda: None,
        get_device_name=lambda i=0: name,
    )
    torch.zeros = zeros
    torch.cuda = cuda
    return torch


def test_preflight_ok_when_cuda_works():
    with patch.dict(sys.modules, {"torch": _fake_torch(available=True)}):
        ok, detail = _preflight_cuda()
    assert ok is True
    assert "FakeGPU" in detail


def test_preflight_fails_when_alloc_raises():
    err = RuntimeError("Error 802: system not yet initialized")
    with patch.dict(sys.modules, {"torch": _fake_torch(alloc_error=err)}):
        ok, detail = _preflight_cuda()
    assert ok is False
    assert "802" in detail
    assert "RuntimeError" in detail


def test_preflight_fails_when_cuda_unavailable():
    with patch.dict(sys.modules, {"torch": _fake_torch(available=False)}):
        ok, detail = _preflight_cuda()
    assert ok is False
    assert "is_available" in detail


def test_preflight_skipped_when_torch_missing():
    # Force `import torch` to fail.
    with patch.dict(sys.modules, {"torch": None}):
        ok, detail = _preflight_cuda()
    assert ok is True
    assert "skipped" in detail


def test_worker_exits_without_claiming_on_bad_gpu(tmp_path):
    """With preflight enabled and a bad GPU, the worker claims nothing and the
    task stays pending."""
    from flexlock.taskdb import queue_tasks, get_status_counts

    db = tmp_path / "run.lock.tasks.db"
    queue_tasks(db, [{"task_id": 0, "save_dir": str(tmp_path / "a")}])

    err = RuntimeError("Error 802: system not yet initialized")
    sentinel = {"claimed": False}

    def boom_claim(*a, **k):
        sentinel["claimed"] = True
        raise AssertionError("worker must not claim a task when preflight fails")

    with patch("flexlock.worker._config.PREFLIGHT_CUDA", True), \
         patch.dict(sys.modules, {"torch": _fake_torch(alloc_error=err)}), \
         patch("flexlock.worker.claim_next_tasks", side_effect=boom_claim):
        worker_loop(func=lambda c: None, cfg={}, task_to=".", db_path=db)

    assert sentinel["claimed"] is False
    assert get_status_counts(db).get("pending", 0) == 1


def test_worker_runs_when_preflight_disabled(tmp_path):
    """Preflight off (default): worker proceeds normally even if torch is absent."""
    from flexlock.taskdb import queue_tasks, get_status_counts

    db = tmp_path / "run.lock.tasks.db"
    sub = tmp_path / "a"
    queue_tasks(db, [{"task_id": 0, "save_dir": str(sub)}])

    with patch("flexlock.worker._config.PREFLIGHT_CUDA", False):
        worker_loop(func=lambda c: {"ok": 1}, cfg={}, task_to=".", db_path=db)

    assert get_status_counts(db).get("done", 0) == 1
