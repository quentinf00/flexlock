"""Terminal queue export must preserve references in unexecuted stages."""
import sqlite3

import yaml
from flexlock.taskdb import queue_tasks, dump_to_yaml


def test_failed_pipeline_export_keeps_missing_producer_reference(tmp_path):
    reference = '${run_lock:' + str(tmp_path / 'never-produced') + ',config.output}'
    task = {'_stages_': [
        {'_target_': 'builtins.dict', 'save_dir': str(tmp_path / 'first')},
        {'_target_': 'builtins.dict', 'save_dir': str(tmp_path / 'second'),
         'input': reference, '_snapshot_': {'data': {'input': reference}}},
    ]}
    database = tmp_path / 'run.lock.tasks.db'
    queue_tasks(database, [task])
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE tasks SET status='failed'")
    output = tmp_path / 'terminal.yaml'
    dump_to_yaml(database, output)
    rows = yaml.safe_load(output.read_text())
    assert rows[0]['status'] == 'failed'
    assert rows[0]['task']['_stages_'][1]['input'] == reference
    assert rows[0]['task']['_stages_'][1]['_snapshot_']['data']['input'] == reference
