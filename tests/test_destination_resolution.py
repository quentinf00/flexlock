"""Scan-local parent reuse retains canonical destination behavior."""
from pathlib import Path

import pytest

from flexlock import destination_guard as guard
from flexlock.taskdb import queue_tasks


def test_parent_reuse_matches_path_resolve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    real = tmp_path/'real';real.mkdir()
    (real/'file').write_text('value')
    (tmp_path/'parent').symlink_to(real, target_is_directory=True)
    (real/'relative').symlink_to('file')
    (real/'absolute').symlink_to(real/'file')
    (real/'dangling').symlink_to('missing')
    resolve = guard._destination_resolver()
    paths = ['/', '.', '..', 'real/..', 'real/.', 'real/file', 'real/missing',
             'parent/file', 'parent/relative', 'parent/absolute', 'parent/dangling',
             'missing/nested/file', 'parent/../real/file', 'real/spaced name',
             str(real/'relative'), str(real/'missing')]
    for path in paths:
        assert resolve(path) == str(Path(path).resolve())


def test_symlink_loop_is_not_treated_as_a_literal_destination(tmp_path):
    loop = tmp_path/'loop';loop.symlink_to('loop')
    with pytest.raises(RuntimeError):
        guard._destination_resolver()(loop)


def test_parent_is_resolved_once_per_scan_and_fresh_next_scan(tmp_path, monkeypatch):
    real = tmp_path/'real';real.mkdir()
    other = tmp_path/'other';other.mkdir()
    parent = tmp_path/'alias';parent.symlink_to(real, target_is_directory=True)
    original = Path.resolve
    calls = []
    def trace(path, *args, **kwargs):
        calls.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'resolve', trace)
    resolve = guard._destination_resolver()
    assert resolve(parent/'a') == str(real/'a')
    assert resolve(parent/'b') == str(real/'b')
    assert calls == [parent]
    parent.unlink();parent.symlink_to(other, target_is_directory=True)
    assert guard._destination_resolver()(parent/'a') == str(other/'a')


def test_parent_symlink_retarget_is_visible_to_next_ownership_check(tmp_path):
    first = tmp_path/'first';first.mkdir()
    second = tmp_path/'second';second.mkdir()
    parent = tmp_path/'alias';parent.symlink_to(first, target_is_directory=True)
    db = tmp_path/'queue'/'run.lock.tasks.db'
    queue_tasks(db, [dict(_stages_=[dict(save_dir=str(parent/'a')),
                                  dict(save_dir=str(parent/'b'))])])
    guard.reserve_queue([first/'b', second/'b'], db)
    assert guard.has_active_destination(first/'b')
    assert not guard.has_active_destination(second/'b')
    parent.unlink();parent.symlink_to(second, target_is_directory=True)
    assert not guard.has_active_destination(first/'b')
    assert guard.has_active_destination(second/'b')
