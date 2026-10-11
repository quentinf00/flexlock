"""Read existing SST contracts and prepare a scratch queue; never execute science."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import runpy
import sys

root = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-11-sst-consumer')
os.environ['FLEXLOCK_CACHE'] = str(root.with_name(root.name+'-hash-cache'))
os.environ['FLEXLOCK_INDEX'] = str(root/'index.db')
pilot = Path('/ontap/user/qfebvre/sst-workflow-pilot')
sys.path.insert(0, str(pilot))
from omegaconf import OmegaConf
from flexlock.sweep_compile import compile_sweep
from flexlock.outputs import validate_outputs
from flexlock.destination_guard import guard_destinations
from flexlock.parallel import ParallelExecutor
from flexlock.utils import collect_task_repos
from flexlock.taskdb import get_all_tasks
from sst_ml_mapping.workflow_reassessment import reassess

cfg = runpy.run_path(str(pilot/'configs/workflow_reassessment.py'))['cfg']['main']
original = Path(cfg['save_dir'])
def checksums():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in original.iterdir() if p.is_file()}
before = checksums()
validate_outputs(OmegaConf.create(cfg))
root.mkdir(parents=True, exist_ok=False)
items = compile_sweep(OmegaConf.create(cfg), [dict(save_dir=str(root/'product'))])
stage = items[0][1]
values = OmegaConf.to_container(stage, resolve=False)
inspect.signature(reassess).bind(**{k:v for k,v in values.items() if not k.startswith('_')})
def forbidden(*args, **kwargs):
    raise AssertionError('Scientific callable must not execute during investigation')
master = OmegaConf.create(dict(save_dir=str(root/'queue'), _snapshot_={}))
with guard_destinations([stage.save_dir], db_dir=master.save_dir):
    executor = ParallelExecutor(func=forbidden, cfg=master, tasks=[stage], task_target=None,
                                _compiled_tasks=True)
    repos = collect_task_repos(master, [stage])
rows = get_all_tasks(executor.db_path)
assert len(rows) == 1 and rows[0]['status'] == 'pending'
assert OmegaConf.to_container(rows[0]['task'], resolve=False) == values
assert set(repos) == {'sst', 'flexlock'}
assert not (root/'product/run.lock').exists() and not (root/'queue/run.lock').exists()
assert checksums() == before
result = dict(consumer='isolated SST frozen-reassessment configuration',
    original= str(original), original_artifact_sha256=before,
    contracts_passed=True, callable_signature_passed=True,
    scratch_queue_pending=1, queued_config_unchanged=True, repositories= repos,
    source_capture=False, scientific_execution=False, scheduler_calls=0,
    original_artifacts_unchanged=True,
    limits='Config/guard/queue/read-contract acceptance only; no source snapshot or scientific replay.')
(root/'validation.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
