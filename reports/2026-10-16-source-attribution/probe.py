"""Local toy source-capture trial. No scientific project or scheduler execution."""
import importlib
import json
import os
from pathlib import Path
import tempfile

from git import Repo
from omegaconf import OmegaConf
from flexlock import Project
from flexlock.diff import RunDiff
from flexlock.record import load_record

report = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='flexlock-stage-scope-') as scratch:
    root = Path(scratch)
    os.environ['FLEXLOCK_INDEX'] = str(root/'index.db')
    os.environ['FLEXLOCK_HASH_ENV'] = '1'
    source = root/'source';source.mkdir()
    repo = Repo.init(source)
    with repo.config_writer() as writer:
        writer.set_value('user','name','Validation')
        writer.set_value('user','email','validation@example.invalid')
    for name in ['a.py','b.py']:(source/name).write_text('# synthetic source\n')
    repo.index.add(['a.py','b.py']);repo.index.commit('fixture')
    module = importlib.import_module('flexlock.snapshot')
    original = module.create_shadow_snapshot
    calls = []
    def capture(*args, **kwargs):
        calls.append(dict(path=args[0], include=kwargs.get('include')))
        return original(*args, **kwargs)
    module.create_shadow_snapshot = capture
    def submit(label):
        cfgs = [OmegaConf.create(dict(
            _target_='examples.slimmer_workflows.stages.prepare',
            save_dir=str(root/label/name), output_path=str(root/label/name/'dataset.json'),
            _snapshot_=dict(discover=dict(repos=False),
                repos={name:dict(path=str(source), include=[name+'.py'])})))
            for name in ['a','b']]
        results = Project().submit_pipeline([cfgs], task_record='db')
        assert all(r.is_success for r in results[0])
        return [load_record(cfg.save_dir) for cfg in cfgs]
    try:
        first = submit('first')
        assert len(calls)==1, calls  # One shared capture, not one per stage.
        (source/'b.py').write_text('# changed second stage source\n')
        second = submit('second')
        assert len(calls)==2, calls
    finally:
        module.create_shadow_snapshot = original
    stages = {}
    for name, record in zip(['a','b'],first):
        stages[name] = dict(source_scope=record['source_scope'],
            captured_files=repo.git.ls_tree('-r','--name-only',record['repos']['a']['tree']).splitlines())
        assert stages[name]['captured_files']==['a.py','b.py']
        assert record['source_scope'][name]['include']==[name+'.py']
    unchanged_a = RunDiff(second[0],first[0]).compare_git()
    changed_b = not RunDiff(second[1],first[1]).compare_git()
    assert unchanged_a and changed_b
    (report/'probe.json').write_text(json.dumps(dict(stages=stages,
        capture_calls=calls, one_shared_capture_per_campaign=True,
        first_stage_matches_after_second_stage_change=unchanged_a,
        second_stage_change_detected=changed_b),indent=2)+'\n')
print('One shared capture per campaign; distinct stage scopes; stage comparisons respect the selected source')
