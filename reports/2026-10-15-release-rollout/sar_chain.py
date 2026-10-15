import json,runpy,tempfile
from pathlib import Path
from flexlock.runner import FlexLockRunner
from flexlock.record import load_record
from sar_ml.pipelines.safe_preprocessing import check_coverage
project=Path('/scale/user/qfebvre/projects/2509_sar_ml/sar-ml-enhanced')
helpers=runpy.run_path(str(project/'tests/test_safe_preprocessing.py'))
base=Path(tempfile.mkdtemp(prefix='sar093-chain-'));listing,safes=helpers['make_inputs'](base)
root=base/'run'
FlexLockRunner().run(['-d','sar_ml.pipelines.preprocessing_cfg.cfg','-s','split','freeze','extract','prepare_train','prepare_val','prepare_test','-o',f'run_dir={root}',f'listing_path={listing}'])
r=check_coverage(root/'extract/bindings.json');assert r['ready']
records={s:load_record(root/s) for s in ['split','membership','extract','dataset/train','dataset/val','dataset/test']}
assert all(v and 'result' in v for v in records.values())
assert all((root/s/'run.complete').exists() for s in records)
out=dict(root=str(root),coverage_ready=r['ready'],produced=len(r['present']),empty=len(r['empty']),stage_results={k:v['result'] for k,v in records.items()})
Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-15-release-rollout/sar-chain.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
