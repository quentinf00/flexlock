"""Return payloads must not overwrite scientific products in serial or queues."""
import json
from pathlib import Path
import pytest
from omegaconf import OmegaConf
from flexlock import Project
from flexlock.record import load_record
from flexlock.run_record import RunRecord


def produce(save_dir):
    Path(save_dir, 'results.json').write_text('{"science": 17}')
    return {'metric': 42}


def consume(save_dir, value):
    assert value == 42
    return {'received': value}


@pytest.mark.parametrize('mode', ['serial', 'dir', 'db', 'pipeline'])
def test_return_and_scientific_product_are_distinct(tmp_path, mode):
    run = tmp_path/'producer'
    cfg=OmegaConf.create(dict(_target_='tests.test_record_results.produce',save_dir=str(run),
        _snapshot_=dict(discover=dict(repos=False)),
        _outputs_=dict(science=dict(path='results.json',sha256=True))))
    project=Project()
    if mode == 'serial':
        project.submit(cfg,smart_run=False)
    elif mode == 'pipeline':
        second=OmegaConf.create(dict(_target_='tests.test_record_results.consume',
            save_dir=str(tmp_path/'consumer'),
            value='${run_lock:'+str(run)+',result.metric}',
            _snapshot_=dict(discover=dict(repos=False))))
        results=project.submit_pipeline([[cfg,second]],sweep_root=str(tmp_path/'queue'))
        assert all(r.is_success for r in results[0])
        assert load_record(tmp_path/'consumer')['result']=={'received':42}
    else:
        project.submit(cfg,sweep=[{}],sweep_root=str(tmp_path/'queue'),
                       smart_run=False,task_record=mode)
    assert json.loads((run/'results.json').read_text())=={'science':17}
    assert load_record(run)['result']=={'metric':42}
    assert RunRecord(run).load_results()=={'metric':42}
    assert (run/'run.complete').exists()
    if mode=='serial':
        cached=project.submit(cfg,smart_run=False,save_dir_policy='skip')
        assert cached.result=={'metric':42}
        project.submit(cfg,smart_run=False,force=True)
        assert json.loads((run/'results.json').read_text())=={'science':17}


def test_new_record_never_reads_scientific_json_as_return(tmp_path):
    record=RunRecord(tmp_path)
    record.write_lock({'config':{}})
    (tmp_path/'results.json').write_text('{"science":17}')
    assert record.load_results() is None
    record.write_results(None)
    assert record.load_results()=={'result':None}
    assert json.loads((tmp_path/'results.json').read_text())=={'science':17}


def test_legacy_result_still_readable(tmp_path):
    (tmp_path/'run.lock').write_text('config: {}\n')
    (tmp_path/'results.json').write_text('{"old":42}')
    assert RunRecord(tmp_path).load_results()=={'old':42}
