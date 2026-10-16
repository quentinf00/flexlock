"""Bounded FlexLock preparation validation; all scheduler boundaries are mocked."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True)
parser.add_argument('--count',type=int,default=1000)
parser.add_argument('--baseline',action='store_true')
parser.add_argument('--tracked',action='store_true')
parser.add_argument('--local',action='store_true')
parser.add_argument('--no-outputs',action='store_true',help='Match the original preparation-only baseline fixture')
args=parser.parse_args()
root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=False)
os.environ['FLEXLOCK_INDEX']=str(root/'index.db')
os.environ['FLEXLOCK_CACHE']=str(root/'cache')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from benchmarks.thousand_items.measure import make_config,command_guard
from flexlock import Project,__version__
from omegaconf import OmegaConf
inputs=root/'inputs';inputs.mkdir()
for i in range(args.count):(inputs/f'{i}.bin').write_bytes(bytes([i%251])*4096)
slurm=root/'slurm.yaml';slurm.write_text("startup_lines: ['#SBATCH --array=0-3', '#SBATCH --cpus-per-task=1']\n")
cfg=OmegaConf.create(make_config(root/'runs',inputs,provenance=args.tracked,data=args.tracked))
if not (args.no_outputs or args.baseline):
 cfg._outputs_ = dict(product=dict(path='product.json', sha256=True))
kw=dict(smart_run=False) if args.baseline else {}
calls,guard=command_guard()
with guard:
 start=time.perf_counter()
 results=Project().submit(cfg,sweep=[dict(item=i) for i in range(args.count)],
     sweep_dir_suffix=True,slurm_config=None if args.local else str(slurm),
     wait=args.local,n_jobs=1,**kw)
 elapsed=time.perf_counter()-start
assert len(results)==args.count and {str(r.status) for r in results}==({'SUCCESS'} if args.local else {'SUBMITTED'})
with sqlite3.connect(root/'runs/run.lock.tasks.db') as db:
 states=db.execute('SELECT status,count(*) FROM tasks GROUP BY status').fetchall()
assert states==[('done' if args.local else 'pending',args.count)] and len(calls)==(0 if args.local else 1)
if args.local:
 from flexlock.record import load_record
 from flexlock.outputs import validate_outputs
 for i,result in enumerate(results):
  record=load_record(result.record_dir)
  validate_outputs(OmegaConf.create(record['config']), result.save_dir, record_dir=result.record_dir)
  assert json.loads((Path(result.save_dir)/'product.json').read_text())['item']==i
 assert {r.get('item') for r in results}==set(range(args.count))
summary=dict(version=__version__,revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 count=args.count,tracked=args.tracked,local=args.local,baseline=args.baseline,
 output_contract=not(args.no_outputs or args.baseline),seconds=elapsed,
 files=sum(p.is_file() for p in root.rglob('*') if not p.is_relative_to(inputs)),
 states=states,scheduler_calls_mocked=len(calls),python=sys.executable,output=str(root))
(root/'measurement.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
