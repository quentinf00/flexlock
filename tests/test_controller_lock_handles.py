"""Parallel handle preparation retains ordered ownership and failure cleanup."""
import threading

import pytest

from flexlock import destination_guard as guard


@pytest.mark.parametrize('workers', [1, 2, 4])
def test_lock_acquisition_stays_sorted_on_controller_thread(tmp_path, monkeypatch, workers):
    monkeypatch.setattr(guard, '_IO_WORKERS', workers)
    calls = []
    original = guard.fcntl.flock
    def flock(fd, flags):
        calls.append((fd.name, threading.get_ident()))
        return original(fd, flags)
    monkeypatch.setattr(guard.fcntl, 'flock', flock)
    paths = [tmp_path/'z', tmp_path/'a', tmp_path/'m']
    with guard.guard_destinations(paths):
        assert [name for name, _ in calls] == [str(path/guard.CONTROLLER_LOCK) for path in sorted(paths)]
        assert all(ident == threading.get_ident() for _, ident in calls)


def test_open_failure_joins_workers_and_closes_every_successful_handle(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, '_IO_WORKERS', 2)
    opened = []
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    errors = []
    original = guard._open_controller_lock
    def opening(path):
        if path == str(tmp_path/'b'):
            assert started.wait(5)
            raise OSError('injected lock open failure')
        if path == str(tmp_path/'c'):
            started.set()
            assert release.wait(5)
        stream = original(path)
        opened.append(stream)
        return stream
    monkeypatch.setattr(guard, '_open_controller_lock', opening)
    def invoke():
        try:
            with guard.guard_destinations([tmp_path/name for name in ('a','b','c')]):
                pytest.fail('guard body started')
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()
    thread = threading.Thread(target=invoke);thread.start()
    try:
        assert started.wait(5)
        assert not finished.is_set()
        assert opened and not any(stream.closed for stream in opened)
    finally:
        release.set();thread.join(5)
    assert not thread.is_alive() and finished.is_set()
    assert len(errors) == 1 and isinstance(errors[0], OSError)
    assert len(opened) == 2 and all(stream.closed for stream in opened)


def test_collision_closes_prepared_handles(tmp_path, monkeypatch):
    from flexlock.exceptions import FlexLockValidationError
    a, b = tmp_path/'a', tmp_path/'b'
    with guard.guard_destinations([a]):
        original = guard._open_controller_lock
        opened = []
        def opening(path):
            stream = original(path);opened.append(stream)
            return stream
        monkeypatch.setattr(guard, '_open_controller_lock', opening)
        with pytest.raises(FlexLockValidationError, match='another controller'):
            with guard.guard_destinations([b, a]):
                pytest.fail('collision entered')
        assert len(opened) == 2 and all(stream.closed for stream in opened)
