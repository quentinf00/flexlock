"""Capture and fingerprint trees share scope, without staging excluded blobs."""
from pathlib import Path
from git import Repo
from omegaconf import OmegaConf
from flexlock.git_utils import create_shadow_snapshot, create_shadow_tree
from flexlock.utils import extract_tracking_info, collect_task_repos


def repository(path):
    path.mkdir()
    r=Repo.init(path)
    with r.config_writer() as c:
        c.set_value('user','name','Test');c.set_value('user','email','test@example.invalid')
    (path/'baseline').write_text('base')
    r.index.add(['baseline']);r.index.commit('base')
    return r


def test_scoped_capture_equals_comparison_and_never_stages_excluded_blob(tmp_path):
    r=repository(tmp_path/'repo');p=Path(r.working_tree_dir)
    (p/'stage.py').write_text('source')
    (p/'array.bin').write_bytes(b'untracked scientific array for scope check')
    excluded=r.git.hash_object(str(p/'array.bin'))
    index=(Path(r.git_dir)/'index').read_bytes()
    capture=create_shadow_snapshot(str(p),include=['stage.py','array.bin'],exclude=['array.bin'])
    comparison=create_shadow_tree(str(p),include=['stage.py','array.bin'],exclude=['array.bin'])
    assert capture['tree']==comparison['tree']
    assert r.git.ls_tree('-r','--name-only',capture['tree']).splitlines()==['stage.py']
    assert not (Path(r.git_dir)/'objects'/excluded[:2]/excluded[2:]).exists()
    assert (Path(r.git_dir)/'index').read_bytes()==index


def test_nested_editable_targets_and_explicit_scope(tmp_path,monkeypatch):
    paths=[]
    for name in ['scopealpha','scopebeta']:
        p=tmp_path/name;repository(p)
        (p/name).mkdir();(p/name/'__init__.py').write_text('')
        (p/name/'stage.py').write_text('def run(**kwargs): pass\n')
        (p/name/'helper.py').write_text('value=42\n')
        monkeypatch.syspath_prepend(str(p));paths.append(p)
    cfg=OmegaConf.create(dict(_target_='scopealpha.stage.run',
        model=dict(_target_='scopebeta.stage.run')))
    repos,_,_=extract_tracking_info(cfg)
    assert set(repos)=={'scopealpha','scopebeta'}
    assert repos['scopebeta']['include']==['scopebeta/stage.py']
    cfg['_snapshot_']=dict(repos=dict(encoder=dict(path=str(paths[1]),include=['scopebeta/'])))
    repos,_,_=extract_tracking_info(cfg)
    assert set(repos)=={'scopealpha','encoder'}
    assert repos['encoder']['include']==['scopebeta/']
    cfg['_snapshot_']['discover']=dict(repos=False)
    assert set(extract_tracking_info(cfg)[0])=={'encoder'}


def test_master_captures_union_of_stage_scopes(tmp_path):
    p=str(tmp_path)
    task=lambda name: dict(_snapshot_=dict(discover=dict(repos=False),
        repos=dict(main=dict(path=p,include=[name]))))
    repos=collect_task_repos(OmegaConf.create({}),[task('a.py'),task('b.py')])
    assert repos['main']['include']==['a.py','b.py']
