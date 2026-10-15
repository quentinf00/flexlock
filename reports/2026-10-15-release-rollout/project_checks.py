"""Bounded provenance/reader checks; no model execution or artifact mutation."""
import json, tempfile,hashlib,subprocess,sys
from pathlib import Path
from flexlock import Project
from flexlock.record import load_record
from flexlock.run_record import RunRecord
from flexlock.git_utils import create_shadow_tree
from omegaconf import OmegaConf
report=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout')
base=Path(tempfile.mkdtemp(prefix='flexlock093-project-check-'))
repos={
'hafs':dict(main=dict(path='/scale/user/qfebvre/projects/260324_jepa/hafs-jepa',include=['src/','scripts/']),geo_jepa=dict(path='/scale/user/qfebvre/projects/260324_jepa/geo-jepa',include=['src/'])),
'biomass':dict(main=dict(path='/scale/user/qfebvre/projects/260617_biomass/biomass_proc',include=['src/','configs/','workflows/','pipeline.py'],exclude=['**/__pycache__/**']))}
results={}
for project,scopes in repos.items():
 p=base/project
 cfg=OmegaConf.create(dict(_target_='builtins.dict',save_dir=str(p),probe=project,
  _snapshot_=dict(discover=dict(repos=False,prevs=False),repos=scopes)))
 outcome=Project().submit(cfg,smart_run=False);assert outcome.is_success
 record=load_record(p);checks={}
 for key,scope in scopes.items():
  tree=create_shadow_tree(**dict(repo_path=scope['path'],include=scope['include'],exclude=scope.get('exclude')))
  assert record['repos'][key]['tree']==tree['tree']
  files=subprocess.check_output(['git','-C',scope['path'],'ls-tree','-r','--name-only',tree['tree']],text=True).splitlines()
  assert files and all(not f.startswith(('results/','reports/','outputs/')) for f in files)
  checks[key]=dict(tree=tree['tree'],files=len(files),include=scope['include'])
 assert RunRecord(p).load_results()['probe']==project
 results[project]=dict(run=str(p),scopes=checks,result_in_record=True)
for name,path in {
'sst':'/scale/user/qfebvre/projects/251218_sst/sst_ml_zarrpatch/reports/flexlock-adoption/runs/20261014-retained003/reassess',
'hafs':'/scale/user/qfebvre/projects/260324_jepa/hafs-jepa/runs/retained-eval/bs_shared8_cont/v1/irar_eval',
'biomass':'/scale/user/qfebvre/projects/260617_biomass/biomass_proc/reports/flexlock-adoption/runs/retained-wave-checked004/assess'}.items():
 record=load_record(path);value=RunRecord(path).load_results()
 assert record and value is not None
 results[name+'_retained_reader']=dict(path=path,result_type=type(value).__name__,record_read=True)
(report/'project-checks.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
