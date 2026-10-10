"""Reuse task text, never mutable queue or filesystem ownership."""
from pathlib import Path
import sqlite3

import pytest
import yaml

from flexlock import destination_guard as guard
from flexlock.taskdb import queue_tasks


@pytest.fixture(autouse=True)
def empty_cache():
    guard._cached_row_paths.cache_clear()
    yield
    guard._cached_row_paths.cache_clear()


def test_repeated_checks_decode_once_but_read_status_each_time(tmp_path, monkeypatch):
    product = tmp_path/'queue'/'product'
    db = product.parent/'run.lock.tasks.db'
    queue_tasks(db, [dict(save_dir=str(product))])
    original = guard._decode_row_paths
    calls = []
    def trace(raw, loader):
        calls.append(raw)
        return original(raw, loader)
    monkeypatch.setattr(guard, '_decode_row_paths', trace)
    assert guard.has_active_destination(product)
    assert guard.has_active_destination(product)
    assert len(calls) == 1
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE tasks SET status='done'")
    assert not guard.has_active_destination(product)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE tasks SET status='running'")
    assert guard.has_active_destination(product)
    assert len(calls) == 1


def test_replacement_database_is_read_fresh(tmp_path):
    product = tmp_path/'queue'/'product'
    db = product.parent/'run.lock.tasks.db'
    queue_tasks(db, [dict(save_dir=str(product))])
    assert guard.has_active_destination(product)
    db.unlink()
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE tasks (task_info TEXT, status TEXT)')
        conn.execute('INSERT INTO tasks VALUES (?, ?)',
                     (yaml.safe_dump(dict(save_dir=str(product.parent/'sibling'))), 'pending'))
    assert not guard.has_active_destination(product)


def test_relative_paths_follow_changed_working_directory(tmp_path, monkeypatch):
    first = tmp_path/'first';first.mkdir()
    second = tmp_path/'second';second.mkdir()
    raw = 'save_dir: product\n'
    monkeypatch.chdir(first)
    assert guard._row_destinations(raw, guard._destination_resolver()) == {str(first/'product')}
    monkeypatch.chdir(second)
    assert guard._row_destinations(raw, guard._destination_resolver()) == {str(second/'product')}
    assert guard._cached_row_paths.cache_info().hits == 1


def test_cache_is_bounded_and_large_documents_bypass_it():
    resolve = lambda value: value
    for i in range(1100):
        assert guard._row_destinations(f'save_dir: /product/{i}\n', resolve) == {f'/product/{i}'}
    assert guard._cached_row_paths.cache_info().currsize == 1024
    before = guard._cached_row_paths.cache_info()
    raw = 'save_dir: /large\nnotes: '+('x' * guard._ROW_CACHE_CHARS)+'\n'
    for _ in range(2):
        assert guard._row_destinations(raw, resolve) == {'/large'}
    assert guard._cached_row_paths.cache_info() == before


def test_cached_paths_are_immutable_and_unresolved():
    raw = '_stages_:\n- save_dir: relative/path\n- save_dir: relative/path\n- save_dir: ${future}\n'
    paths = guard._cached_row_paths(raw, guard._TASK_LOADER)
    assert paths == frozenset(['relative/path'])
    with pytest.raises(AttributeError):
        paths.add('/changed')


def test_loader_identity_is_part_of_cache_key(monkeypatch):
    raw = 'save_dir: /product\ncreated: 2026-10-10\n'
    for loader in {yaml.SafeLoader, getattr(yaml, 'CSafeLoader', yaml.SafeLoader)}:
        monkeypatch.setattr(guard, '_TASK_LOADER', loader)
        assert guard._row_destinations(raw, str) == {'/product'}
    assert guard._cached_row_paths.cache_info().currsize == len({yaml.SafeLoader, getattr(yaml, 'CSafeLoader', yaml.SafeLoader)})


def test_parse_errors_are_not_cached():
    for _ in range(2):
        with pytest.raises(yaml.YAMLError):
            guard._row_destinations('save_dir: [', str)
    info = guard._cached_row_paths.cache_info()
    assert info.currsize == 0 and info.misses == 2
