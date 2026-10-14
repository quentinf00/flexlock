import hashlib,inspect,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
NF=Path('/scale/user/qfebvre/projects/250930_maxss_era5pp/maxss-ml/.claude/worktrees/neural-field')
PROJECT=Path('/scale/user/qfebvre/projects/250930_maxss_era5pp')
from omegaconf import OmegaConf
import flexlock
import maxss_configs.train.neural_field as configs
from maxss_diff.train_neural_field import main
from flexlock.sweep_compile import compile_sweep
retained=PROJECT/'results_hafs/product_bench/hist/nf_wknot5_v05_cens20_sarpatch'
before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in retained.iterdir() if p.is_file()}
assert flexlock.__version__=='0.9.2' and '/site-packages/' in flexlock.__file__
assert str(NF) in configs.__file__
old=OmegaConf.create(configs.cfg_smoke)
out=ROOT/'runs/neural-field/global-smoke/acceptance-001/train'
items=compile_sweep(old,[{'save_dir':str(out)}])
new=OmegaConf.to_container(items[0][1],resolve=True)
assert new['trainer']['callbacks'][0]['dirpath']==str(out/'checkpoints')
assert new['trainer']['logger']['_args_'][0]==str(out)
assert new['datamodule']['val_cache_path']==configs.cfg_smoke['datamodule']['val_cache_path']
inspect.signature(main).bind(**{k:v for k,v in new.items() if not k.startswith('_')})
assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in retained.iterdir() if p.is_file()}
(ROOT/'nf-resolved-config.json').write_text(json.dumps(new,indent=2)+'\n')
report=dict(version=flexlock.__version__,library=flexlock.__file__,config_source=configs.__file__,
 signature_passed=True,logger_checkpoint_paths_follow_save_dir=True,
 validation_panel_path_preserved=True,retained_run=str(retained),retained_sha256=before,
 retained_artifacts_unchanged=True,training=False,inference=False,scheduler_submission=False)
(ROOT/'nf-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
