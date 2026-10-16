"""Read-only bounded source audit; generated records and nested libraries excluded."""
import json
from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent
source=r.parent/'2026-10-15-release-rollout/caller-audit.json'
roots=[x['root'] for x in json.loads(source.read_text())]
roots += ['/ontap/user/qfebvre/flexlock-workflow-lab','/ontap/user/qfebvre/sar-ml-workflow-pilot']
pattern=r'''smart_run\s*=\s*True|--check-exists|submit_chained|ChainedResult|\.run_stage\(|_skip_complete_|save_dir_policy\s*=\s*["']skip["']|\b(?:proj|project)\.(?:exists|get_result)\('''
rows=[]
for root in dict.fromkeys(roots):
 if not Path(root).exists():continue
 argv=['rg','-n','--glob','*.py','--glob','*.sh','--glob','*.yaml','--glob','*.yml',
       '--glob','!**/reports/**','--glob','!**/results*/**','--glob','!**/runs/**',
       '--glob','!**/flexlock/**','--glob','!**/.pixi/**','--glob','!**/vendor/**',pattern,'.']
 p=subprocess.run(argv,cwd=root,text=True,capture_output=True,timeout=45)
 assert p.returncode in (0,1),(root,p.stderr)
 rows.append(dict(root=root,hits=p.stdout.splitlines(),coverage='literal Python/shell/YAML; excludes generated reports/results/runs, nested library/vendor/env trees; dynamic use and uninspected notebooks remain outside this audit'))
(r/'caller-inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(dict(roots=len(rows),roots_with_hits=sum(bool(x['hits']) for x in rows),hits=sum(len(x['hits']) for x in rows))))
