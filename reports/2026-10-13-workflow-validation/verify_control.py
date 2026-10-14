import json,sqlite3
from pathlib import Path
from flexlock.record import load_record
from flexlock.outputs import validate_outputs
ROOT=Path(__file__).resolve().parent
run=ROOT/'runs/scheduler-control/linear/acceptance-001'
with sqlite3.connect((run/'run.lock.tasks.db').resolve().as_uri()+'?mode=ro',uri=True) as c:
 rows=c.execute('SELECT task_id,status,job_id,node,error FROM tasks').fetchall()
assert len(rows)==1 and rows[0][1]=='done' and rows[0][2]=='1352647' and not rows[0][4]
records={name:load_record(run/name) for name in ['prepare','train','assess']}
for name,r in records.items():validate_outputs(r['config'],run/name)
report=json.loads((run/'assess/report.json').read_text());assert report=={'count':3,'total':12}
assert records['train']['config']['input_path']==str(run/'prepare/dataset.json')
assert records['assess']['config']['checkpoint_path']==str(run/'train/model.json')
summary=dict(job_id=rows[0][2],node=rows[0][3],status=rows[0][1],stages=list(records),
 output_contracts_passed=True,exact_upstream_paths=True,assessment=report,
 real_slurm=True,gpu_requested=False,resource_limit='1 CPU / 2 GB / 3 minutes',
 frontend_reporting_error='Initial launcher assumed Python return values with --print-job-id; job completed; reporting recovered from authoritative queue; no resubmission')
(ROOT/'slurm-validation.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
