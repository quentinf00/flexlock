"""Selected queue reads retain history while avoiding irrelevant payload decoding."""
import sqlite3

import pytest
from omegaconf import OmegaConf
from flexlock.api import Project
from flexlock.record import _list_task_records, list_task_records
from flexlock.taskdb import queue_tasks, finish_task, _hash_task


def test_terminal_selection_does_not_decode_pending_payloads(tmp_path):
    db = tmp_path/'tasks.db'
    done, pending = dict(item=1), dict(item=2)
    queue_tasks(db, [done, pending], tag='original')
    finish_task(db, done, result=dict(value=11))
    # A receipt-validation query must not decode a pending row at all.
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE tasks SET task_info=? WHERE task_id=?', ('[broken yaml', _hash_task(pending)))
    records = _list_task_records(db, statuses=('done', 'failed', 'interrupted'))
    assert len(records) == 1 and records[0]['result'] == dict(value=11)
    assert records[0]['task'] == done and records[0]['tag'] == 'original'


def test_result_collection_skips_unrelated_payloads_and_keeps_cross_tag_history(tmp_path):
    db = tmp_path/'tasks.db'
    requested = OmegaConf.create(dict(item=1, save_dir=str(tmp_path/'product')))
    unrelated = dict(item=2)
    queue_tasks(db, [requested], tag='old')
    queue_tasks(db, [unrelated], tag='other')
    finish_task(db, requested, result=dict(value=11))
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE tasks SET task_info=? WHERE task_id=?', ('[broken yaml', _hash_task(unrelated)))
    [(index, result)] = Project.collect_results([7], [requested], db, tag='new', job_id='88')
    assert index == 7 and result.status == 'SUCCESS' and result.result == dict(value=11)
    assert result.task_id == _hash_task(requested) and result.job_id == '88'
    assert result.save_dir == str(tmp_path/'product')


@pytest.mark.parametrize('status', ['pending', 'running', 'done', 'failed', 'interrupted'])
def test_selected_reader_preserves_legacy_record_shape(tmp_path, status):
    db = tmp_path/'legacy.db'
    # Historical DBs do not carry tag, snapshot, job_id or modern metadata.
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE tasks(task_id TEXT PRIMARY KEY, task_info TEXT, result_info TEXT, status TEXT)')
        conn.execute('INSERT INTO tasks VALUES(?,?,?,?)', ('legacy', 'save_dir: /old/run\nitem: 1', 'value: 11', status))
    expected = list_task_records(db)
    assert _list_task_records(db, task_ids={'legacy'}, statuses=(status,)) == expected
    assert expected[0]['record_dir'] == '/old/run' and expected[0]['tag'] is None
    assert expected[0]['snapshot'] == {} and expected[0]['result'] == dict(value=11)
    assert _list_task_records(db, task_ids=set()) == []
    assert _list_task_records(db, statuses=()) == []
