"""Submit only with a fresh run label; parse the CLI job ID, not Python results."""
import json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
run=sys.argv[1] if len(sys.argv)>1 else None
if not run:raise SystemExit('Provide a fresh run label; never resubmit an accepted run to repair reporting.')
command=[sys.executable,'-m','flexlock.run_cli','-d','examples.slimmer_workflows.cfgmod.cfg',
 '-s','prepare','train','assess','-o',f'runs_root={ROOT}/runs','track=scheduler-control',
 'arm=linear',f'run={run}','--slurm-config',str(ROOT/'slurm_cpu_control.yaml'),'--print-job-id']
result=subprocess.run(command,check=True,text=True,stdout=subprocess.PIPE)
job_id=result.stdout.strip()
if not re.fullmatch(r'\d+(?:_\d+)?',job_id):raise ValueError(f'Unexpected job-ID output: {job_id!r}; inspect queue/scheduler before retrying')
with (ROOT/f'{run}-submission.json').open('x') as f:json.dump(dict(job_id=job_id,command=command,status='submitted'),f,indent=2)
print(job_id)
