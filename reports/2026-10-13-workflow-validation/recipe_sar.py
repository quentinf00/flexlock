"""Existing split protocol, organized as one explicit config and a fresh run.

The arm is a label. Changing it does not change the splitting algorithm.
Extraction/dataset adoption is pending an explicit empty/coverage contract.
"""
from flexlock import py2cfg
from sar_ml.stages.data import split_safes
cfg=dict(
 runs_root='/ontap/user/qfebvre/workflow-transition-validation/20261013/runs',
 track='sar-data',arm='legacy-split-plumbing',run='acceptance-003',
 run_dir='${runs_root}/${track}/${arm}/${run}',
 listing_path='/ontap/user/qfebvre/work/projects/2509_sar_ml/sar-ml-enhanced/data/listings/b08_listing_hpc.csv',
 split=py2cfg(split_safes,safes_listing_path='${listing_path}',seed=1234,val_prop=0.25,
  group_by_datatake=False,holdout_months=None,save_dir='${run_dir}/split',
  train_safe_path='${.save_dir}/train.txt',val_safe_path='${.save_dir}/val.txt',test_safe_path='${.save_dir}/test.txt',
  _snapshot_=dict(repos=dict(sar='/ontap/user/qfebvre/work/projects/2509_sar_ml/sar-ml-enhanced'),
   data=dict(listing='${...safes_listing_path}')),
  _outputs_={name:dict(path=name+'.txt',sha256=True) for name in ['train','val','test']}))
