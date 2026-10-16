"""Completed composite producers can feed nested dispatch, without losing guards."""
import json,sqlite3
from pathlib import Path
import pytest
from omegaconf import OmegaConf
from flexlock import Project
from flexlock.record import load_record
from flexlock.resolvers import bind_existing_run_locks
from flexlock.taskdb import queue_tasks,update_task_snapshot,_hash_task
from flexlock.run_record import RunRecord
from flexlock.exceptions import FlexLockValidationError


def take(save_dir,value):
    return {'value':value}


def dispatch(save_dir,producer):
    cfg=OmegaConf.create(dict(_target_='tests.test_completed_stage_binding.take',
        save_dir=str(Path(save_dir)/'items/item'),
        value='${run_lock:'+producer+',result.value}',
        _snapshot_=dict(discover=dict(repos=False,prevs=False))))
    result=Project().submit(cfg,sweep=[{}],sweep_root=str(Path(save_dir)/'queue'))
    assert result[0].is_success
    return result[0].result


def test_completed_stage_feeds_nested_sweep(tmp_path,monkeypatch):
    monkeypatch.setattr('flexlock.worker.time.sleep',lambda _:None)
    cfg=lambda target,path,**kw:OmegaConf.create(dict(_target_=target,save_dir=str(path),
        _snapshot_=dict(discover=dict(repos=False,prevs=False)),**kw))
    producer=tmp_path/'producer'
    a=cfg('tests.test_completed_stage_binding.take',producer,value=42)
    b=cfg('tests.test_completed_stage_binding.dispatch',tmp_path/'controller',producer=str(producer))
    results=Project().submit_pipeline([[a,b]],sweep_root=str(tmp_path/'pipeline'))
    assert all(x.is_success for x in results[0])
    assert load_record(tmp_path/'controller')['result']=={'value':42}


@pytest.mark.parametrize('case',['missing_snapshot','other_owner','pending'])
def test_completion_marker_does_not_waive_other_ownership(tmp_path,case):
    d=tmp_path/'producer';d.mkdir()
    config=dict(save_dir=str(d),value=42)
    task={'_stages_':[config]};db=tmp_path/'run.lock.tasks.db'
    queue_tasks(db,[task]);identity=_hash_task(task)
    snapshot={'config':config}
    if case!='missing_snapshot':update_task_snapshot(db,identity,{'stages':{str(d):snapshot}})
    with sqlite3.connect(db) as c:
        if case!='pending':c.execute("UPDATE tasks SET status='running'")
    RunRecord(d).write_lock(snapshot);RunRecord(d).mark_complete()
    (d/'.flexlock_marker').write_text(json.dumps(dict(db=str(db),task_id=identity)))
    if case=='other_owner':queue_tasks(db,[dict(save_dir=str(d),other=True)])
    cfg=OmegaConf.create(dict(value='${run_lock:'+str(d)+',config.value}'))
    with pytest.raises(Exception,match='pending/running'):
        bind_existing_run_locks(cfg)
