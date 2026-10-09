"""Safe ownership parsing must preserve historical rows and fresh state."""
import sqlite3

import pytest
import yaml

from flexlock import destination_guard as guard
from flexlock.exceptions import FlexLockValidationError
from flexlock.taskdb import queue_tasks


@pytest.mark.parametrize('loader', [yaml.SafeLoader, getattr(yaml, 'CSafeLoader', yaml.SafeLoader)])
@pytest.mark.parametrize('shape', ['plain', 'pipeline', 'alias', 'unknown', 'interpolated'])
def test_ownership_loader_preserves_queue_shapes(tmp_path, monkeypatch, loader, shape):
    monkeypatch.setattr(guard, '_TASK_LOADER', loader)
    product = tmp_path/'queue'/'product'
    db = product.parent/'run.lock.tasks.db'
    queue_tasks(db, [dict(save_dir=str(product))])
    quoted = yaml.safe_dump(str(product)).strip().removesuffix('\n...')
    rows = {
        'plain': f'save_dir: {quoted}\ncreated: 2026-10-09\nflag: yes\n',
        'pipeline': f'_stages_:\n- save_dir: {quoted}\n- save_dir: /elsewhere\n',
        'alias': f'base: &stage\n  save_dir: {quoted}\n_stages_: [*stage]\n',
        'unknown': 'item: 1\n',
        'interpolated': 'save_dir: ${unresolved}\n',
    }
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE tasks SET task_info=?', (rows[shape],))
    assert guard.has_active_destination(product)
    with pytest.raises(FlexLockValidationError, match='pending/running'):
        with guard.guard_destinations([product]):
            pytest.fail('active destination entered')


def test_status_and_task_edits_are_visible_between_reads(tmp_path):
    product = tmp_path/'queue'/'product'
    db = product.parent/'run.lock.tasks.db'
    queue_tasks(db, [dict(save_dir=str(product))])
    assert guard.has_active_destination(product)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE tasks SET status='done'")
    assert not guard.has_active_destination(product)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE tasks SET status='pending', task_info=?",
                     (yaml.safe_dump(dict(save_dir=str(product.parent/'sibling'))),))
    assert not guard.has_active_destination(product)
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE tasks SET task_info=?', (yaml.safe_dump(dict(save_dir=str(product))),))
    assert guard.has_active_destination(product)


def test_symlink_destination_is_resolved_again_between_reads(tmp_path):
    first = tmp_path/'first';first.mkdir()
    second = tmp_path/'second';second.mkdir()
    alias = tmp_path/'alias';alias.symlink_to(first, target_is_directory=True)
    db = tmp_path/'queue'/'run.lock.tasks.db'
    queue_tasks(db, [dict(save_dir=str(alias))])
    guard.reserve_queue([first, second], db)
    assert guard.has_active_destination(first)
    assert not guard.has_active_destination(second)
    alias.unlink();alias.symlink_to(second, target_is_directory=True)
    assert not guard.has_active_destination(first)
    assert guard.has_active_destination(second)


@pytest.mark.parametrize('loader', [yaml.SafeLoader, getattr(yaml, 'CSafeLoader', yaml.SafeLoader)])
@pytest.mark.parametrize('row', ['save_dir: [', '!!python/object/apply:os.system [echo unsafe]'])
def test_invalid_or_unsafe_yaml_never_enters_guard(tmp_path, monkeypatch, loader, row):
    monkeypatch.setattr(guard, '_TASK_LOADER', loader)
    product = tmp_path/'queue'/'product'
    db = product.parent/'run.lock.tasks.db'
    queue_tasks(db, [dict(save_dir=str(product))])
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE tasks SET task_info=?', (row,))
    with pytest.raises(yaml.YAMLError):
        guard.has_active_destination(product)
    with pytest.raises(yaml.YAMLError):
        with guard.guard_destinations([product]):
            pytest.fail('invalid row entered')
