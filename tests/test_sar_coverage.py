"""Real SQLite queue fixtures; no SAR extraction or scheduler submission."""
import pytest

from flexlock import taskdb
from flexlock.record import list_task_records
from examples.slimmer_workflows.sar_coverage import check_coverage, bind_membership


def campaign(tmp_path):
    database = tmp_path / 'run.lock.tasks.db'
    tasks = [dict(_target_='sar_ml.stages.data.extract_features',
                  safe=str(tmp_path / f'{name}.SAFE'), save_dir=str(tmp_path / name))
             for name in ['one', 'two']]
    taskdb.queue_tasks(database, tasks)
    rows = list_task_records(database)
    items = [dict(task_id=row['task_id'], safe=row['config']['safe'],
                  save_dir=row['config']['save_dir']) for row in rows]
    manifest = dict(database=str(database), extractor_target=tasks[0]['_target_'], items=items)
    csv = tmp_path / 'one/feats/one_features.csv'
    csv.parent.mkdir(parents=True)
    csv.write_text('name,value\none,1\n')
    return manifest, tasks


def test_done_present_and_done_empty_are_accepted(tmp_path):
    manifest, tasks = campaign(tmp_path)
    for task in tasks:
        taskdb.finish_task(tmp_path / 'run.lock.tasks.db', task)
    report = check_coverage(manifest)
    assert report['ready']
    assert report['empty'] == [tasks[1]['safe']]
    assert report['present'][0]['safe'] == tasks[0]['safe']


def test_binding_uses_frozen_membership_and_refuses_overwrite(tmp_path):
    manifest, tasks = campaign(tmp_path)
    expected = [dict(safe=t['safe'], save_dir=t['save_dir']) for t in tasks]
    output = tmp_path / 'campaign.json'
    bound = bind_membership(tmp_path / 'run.lock.tasks.db', expected,
                            manifest['extractor_target'], output)
    assert {i['task_id'] for i in bound['items']} == {i['task_id'] for i in manifest['items']}
    with pytest.raises(FileExistsError):
        bind_membership(tmp_path / 'run.lock.tasks.db', expected, manifest['extractor_target'], output)


@pytest.mark.parametrize('damage', ['missing', 'ambiguous', 'duplicate'])
def test_binding_cannot_shrink_or_guess_expected_cohort(tmp_path, damage):
    manifest, tasks = campaign(tmp_path)
    expected = [dict(safe=t['safe'], save_dir=t['save_dir']) for t in tasks]
    if damage == 'missing':
        expected.append(dict(safe=str(tmp_path / 'absent.SAFE'), save_dir=str(tmp_path / 'absent')))
    elif damage == 'ambiguous':
        taskdb.queue_tasks(tmp_path / 'run.lock.tasks.db', [dict(tasks[0], cwaves=False)])
    else:
        expected.append(expected[0])
    output = tmp_path / 'campaign.json'
    with pytest.raises(ValueError):
        bind_membership(tmp_path / 'run.lock.tasks.db', expected, manifest['extractor_target'], output)
    assert not output.exists()


@pytest.mark.parametrize('status', ['pending', 'running', 'failed', 'interrupted'])
def test_non_success_blocks_even_when_csv_exists(tmp_path, status):
    manifest, tasks = campaign(tmp_path)
    for task in tasks:
        taskdb.finish_task(tmp_path / 'run.lock.tasks.db', task)
    taskdb.finish_task(tmp_path / 'run.lock.tasks.db', tasks[0], status=status)
    report = check_coverage(manifest)
    assert not report['ready']
    assert any(status in issue for issue in report['issues'])


@pytest.mark.parametrize('damage', ['missing_task', 'wrong_safe', 'wrong_destination',
                                   'missing_database', 'all_empty', 'duplicate'])
def test_incomplete_or_wrong_campaign_is_refused(tmp_path, damage):
    manifest, tasks = campaign(tmp_path)
    for task in tasks:
        taskdb.finish_task(tmp_path / 'run.lock.tasks.db', task)
    if damage == 'missing_task':
        manifest['items'][0]['task_id'] = 'unknown'
    elif damage == 'wrong_safe':
        manifest['items'][0]['safe'] = str(tmp_path / 'other.SAFE')
    elif damage == 'wrong_destination':
        manifest['items'][0]['save_dir'] = str(tmp_path / 'other')
    elif damage == 'missing_database':
        manifest['database'] = str(tmp_path / 'absent.db')
    elif damage == 'all_empty':
        (tmp_path / 'one/feats/one_features.csv').unlink()
    elif damage == 'duplicate':
        manifest['items'].append(manifest['items'][0])
        with pytest.raises(ValueError, match='Duplicate'):
            check_coverage(manifest)
        return
    report = check_coverage(manifest)
    assert not report['ready'] and report['issues']
