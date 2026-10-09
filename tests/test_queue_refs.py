"""Selected producer ownership uses current, legacy and ancestor locators."""
import json
from pathlib import Path
import sqlite3

import pytest
from omegaconf import OmegaConf
from omegaconf.errors import InterpolationResolutionError

from flexlock import destination_guard as guard
from flexlock import queue_refs
from flexlock.exceptions import FlexLockValidationError
from flexlock.resolvers import bind_existing_run_locks
from flexlock.run_record import RunRecord
from flexlock.taskdb import queue_tasks, claim_next_task


def queued(root, product, status='pending', *, task=None):
    db = root/'run.lock.tasks.db'
    queue_tasks(db, [task or dict(save_dir=str(product), item=1)])
    if status == 'running':
        claim_next_task(db, 'test')
    elif status != 'pending':
        with sqlite3.connect(db) as conn:
            conn.execute('UPDATE tasks SET status=?', (status,))
    return db


@pytest.mark.parametrize('status', ['pending', 'running', 'done', 'failed', 'interrupted'])
@pytest.mark.parametrize('locator', ['ancestor', 'pointer', 'relative_marker', 'absolute_marker'])
def test_selected_producer_reads_all_existing_locator_formats(tmp_path, status, locator):
    product = tmp_path/'queue'/'nested'/'product' if locator == 'ancestor' else tmp_path/'products'/'product'
    product.mkdir(parents=True)
    db = queued(tmp_path/'queue', product, status)
    if locator == 'pointer':
        guard.reserve_queue([product], db)
    elif locator.endswith('marker'):
        db_value = str(db) if locator == 'absolute_marker' else '../queue/run.lock.tasks.db'
        (product/queue_refs.MARKER_NAME).write_text(json.dumps(dict(db=db_value, task_id='identity')))
    before = db.read_bytes()
    assert guard.has_active_destination(product) == (status in ('pending', 'running'))
    assert db.read_bytes() == before


@pytest.mark.parametrize('state', ['pending', 'running'])
def test_old_artifact_is_not_bound_while_nested_replacement_is_active(tmp_path, state):
    product = tmp_path/'queue'/'nested'/'product'
    RunRecord(product).write_lock(dict(config=dict(value=41), timestamp='old'))
    queued(tmp_path/'queue', product, state)
    cfg = OmegaConf.create(dict(value='${run_lock:'+str(product)+',config.value}'))
    with pytest.raises(InterpolationResolutionError, match='pending/running work'):
        bind_existing_run_locks(cfg)
    future = bind_existing_run_locks(cfg, allow_future=True)
    assert OmegaConf.to_container(future, resolve=False)['value'] == '${run_lock:'+str(product)+',config.value}'
    assert not future.get('_snapshot_', {}).get('run_lock_reads')


def test_terminal_stale_pointer_cannot_hide_active_ancestor_queue(tmp_path):
    product = tmp_path/'new'/'product'
    old = queued(tmp_path/'old', product, 'done')
    guard.reserve_queue([product], old)
    queued(tmp_path/'new', product)
    assert guard.has_active_destination(product)


def test_pending_sibling_does_not_block_completed_selected_producer(tmp_path):
    product = tmp_path/'queue'/'product'
    RunRecord(product).write_lock(dict(config=dict(value=41), timestamp='old'))
    queued(tmp_path/'queue', product, task=dict(save_dir=str(tmp_path/'queue'/'sibling')))
    assert not guard.has_active_destination(product)
    cfg = OmegaConf.create(dict(value='${run_lock:'+str(product)+',config.value}'))
    assert bind_existing_run_locks(cfg).value == 41


def test_unlocatable_active_row_fails_closed(tmp_path):
    product = tmp_path/'queue'/'product'
    queued(tmp_path/'queue', product, task=dict(item=1))
    assert guard.has_active_destination(product)


@pytest.mark.parametrize('name', [queue_refs.QUEUE_POINTER, queue_refs.MARKER_NAME])
@pytest.mark.parametrize('contents', ['{', '[]', '{}', '{"db": null, "task_db": null}'])
def test_malformed_locators_prevent_binding_and_controller_mutation(tmp_path, name, contents):
    product = tmp_path/'product'
    product.mkdir()
    (product/name).write_text(contents)
    with pytest.raises(FlexLockValidationError, match='Unreadable'):
        guard.has_active_destination(product)
    with pytest.raises(FlexLockValidationError, match='Unreadable'):
        with guard.guard_destinations([product]):
            pytest.fail('guard body started')


def test_missing_pointer_db_fails_closed_but_archived_marker_lock_remains_readable(tmp_path):
    product = tmp_path/'product'
    RunRecord(product).write_lock(dict(config=dict(value=41)))
    pointer = product/queue_refs.QUEUE_POINTER
    pointer.write_text(json.dumps(dict(task_db=str(tmp_path/'missing.db'))))
    with pytest.raises(FlexLockValidationError, match='missing queue'):
        guard.has_active_destination(product)
    pointer.unlink()
    (product/queue_refs.MARKER_NAME).write_text(json.dumps(dict(db='missing.db', task_id='old')))
    assert not guard.has_active_destination(product)
    cfg = OmegaConf.create(dict(value='${run_lock:'+str(product)+',config.value}'))
    assert bind_existing_run_locks(cfg).value == 41


def test_references_are_deduplicated_and_absent_paths_are_not_created(tmp_path, monkeypatch):
    product = tmp_path/'queue'/'product'
    db = queued(tmp_path/'queue', product, 'done')
    guard.reserve_queue([product], db)
    (product/queue_refs.MARKER_NAME).write_text(json.dumps(dict(db='run.lock.tasks.db', task_id='old')))
    calls = []
    original = guard._active_rows
    def trace(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(guard, '_active_rows', trace)
    assert not guard.has_active_destination(product)
    assert calls == [db.resolve()]
    absent = tmp_path/'uncreated'/'product'
    assert not guard.has_active_destination(absent)
    assert not absent.parent.exists()


def test_record_and_query_share_marker_readers():
    from flexlock import record, query, run_record
    assert record.read_marker is query._read_marker is run_record.read_marker is queue_refs.read_marker
    assert record.marker_db is query._resolve_marker_db is queue_refs.marker_db
