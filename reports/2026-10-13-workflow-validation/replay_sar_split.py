import csv,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROJECT=Path('/ontap/user/qfebvre/work/projects/2509_sar_ml/sar-ml-enhanced')
os.environ['FLEXLOCK_CACHE']=str(ROOT/'sar-hash-cache')
os.environ['FLEXLOCK_INDEX']=str(ROOT/'sar-index.db')
import flexlock
from flexlock import Project,py2cfg
from flexlock.record import load_record
from sar_ml.stages.data import split_safes
source=PROJECT/'data/listings/b08_listing_hpc.csv'
before=hashlib.sha256(source.read_bytes()).hexdigest()
out=ROOT/'runs/sar-data/legacy-split-plumbing/acceptance-002/split'
cfg=py2cfg(split_safes,safes_listing_path=str(source),seed=1234,val_prop=0.25,
 save_dir=str(out),train_safe_path=str(out/'train.txt'),val_safe_path=str(out/'val.txt'),
 test_safe_path=str(out/'test.txt'),group_by_datatake=False,holdout_months=None,
 _snapshot_=dict(repos=dict(sar=str(PROJECT)),data=dict(listing=str(source))),
 _outputs_={name:dict(path=name+'.txt',sha256=True) for name in ['train','val','test']})
result=Project().submit(cfg,smart_run=False);result.raise_on_failure()
with source.open() as f:rows=list(csv.DictReader(f))
key=next(iter(rows[0]))
trainval={r[key] for r in rows if r['avail_train'].lower()=='true'}
test={r[key] for r in rows if r['avail_test'].lower()=='true'}
outputs={name:set((out/(name+'.txt')).read_text().splitlines()) for name in ['train','val','test']}
assert not outputs['train']&outputs['val'] and not (outputs['train']|outputs['val'])&outputs['test']
assert outputs['train']|outputs['val']==trainval and outputs['test']==test
assert hashlib.sha256(source.read_bytes()).hexdigest()==before
record=load_record(out);assert record['data'] and record['repos']
report=dict(version=flexlock.__version__,library=flexlock.__file__,status=str(result.status),
 source=str(source),listing_sha256=before,source_unchanged=True,save_dir=str(out),
 counts={k:len(v) for k,v in outputs.items()},coverage_complete=True,disjoint=True,
 protocol='Existing legacy random split; seed1234/val0.25; no change to test eligibility; not a leakage-safe new experiment',
 training=False,feature_extraction=False)
(ROOT/'sar-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
