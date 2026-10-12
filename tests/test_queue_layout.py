"""Fresh layout reservations retain ownership and historical locators."""
import json
import sqlite3

import pytest
from omegaconf import OmegaConf
from omegaconf.errors import InterpolationResolutionError

from flexlock.destination_guard import reserve_queue, has_active_destination, guard_destinations
from flexlock.exceptions import FlexLockValidationError
from flexlock.queue_refs import QUEUE_POINTER
from flexlock.taskdb import queue_tasks
from flexlock.resolvers import bind_existing_run_locks


@pytest.mark.parametrize('status', ['pending', 'running'])
def test_nested_layout_blocks_reuse_of_old_artifact(tmp_path, status):
    db = tmp_path / 'run.lock.tasks.db'
    product = tmp_path / 'runs' / 'one'
    product.mkdir(parents=True)
    (product / 'run.lock').write_text('config:\n  output_path: old-artifact\n')
    queue_tasks(db, [{'task_id': 'one', 'save_dir': str(product)}])
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE tasks SET status = ?', (status,))
    reserve_queue([product], db)
    assert not (product / QUEUE_POINTER).exists()
    assert has_active_destination(product)
    cfg = OmegaConf.create({'input': '${run_lock:' + str(product) + ',config.output_path}'})
    with pytest.raises(InterpolationResolutionError, match='pending/running'):
        bind_existing_run_locks(cfg)
    future = bind_existing_run_locks(cfg, allow_future=True)
    assert OmegaConf.to_container(future, resolve=False) == OmegaConf.to_container(cfg, resolve=False)
    with pytest.raises(FlexLockValidationError, match='pending/running'):
        with guard_destinations([product]):
            pytest.fail('active destination must not be reusable')
    with sqlite3.connect(db) as conn:
        assert dict(conn.execute('SELECT key, value FROM flexlock_metadata')) == {
            'queue_layout': '2', 'minimum_reader': '0.9.1'}


def test_existing_and_external_pointers_retained(tmp_path):
    root = tmp_path / 'queue'
    root.mkdir()
    db = root / 'run.lock.tasks.db'
    nested = root / 'old'
    nested.mkdir()
    (nested / QUEUE_POINTER).write_text('{}')
    external = tmp_path / 'external'
    queue_tasks(db, [{'task_id': str(i), 'save_dir': str(path)}
                     for i, path in enumerate([nested, external])])
    reserve_queue([nested, external], db)
    for product in [nested, external]:
        assert json.loads((product / QUEUE_POINTER).read_text())['task_db'] == str(db)
        assert has_active_destination(product)


def test_nonstandard_database_keeps_explicit_pointer(tmp_path):
    db = tmp_path / 'custom.db'
    product = tmp_path / 'product'
    queue_tasks(db, [{'task_id': 'one', 'save_dir': str(product)}])
    reserve_queue([product], db)
    assert (product / QUEUE_POINTER).exists()
    assert has_active_destination(product)
