import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['FLEXLOCK_CACHE']=str(ROOT/'hash-cache')
os.environ['FLEXLOCK_INDEX']=str(ROOT/'index.db')
import flexlock
from flexlock.api import Project
from flexlock.record import load_record
from flexlock.outputs import validate_outputs
from recipe_sst import cfg
BASELINE=Path('/ontap/user/qfebvre/sst-workflow-pilot/workflow-results/reassessment-20261006')
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in BASELINE.iterdir() if p.is_file()}
assert flexlock.__version__=='0.9.2' and '/site-packages/' in flexlock.__file__
project=Project(defaults=cfg)
result=project.submit(project.get('assess'),smart_run=False)
result.raise_on_failure()
record=load_record(result.save_dir)
validate_outputs(record['config'],result.save_dir)
new=json.loads((Path(result.save_dir)/'assessment.json').read_text())
old=json.loads((BASELINE/'assessment.json').read_text())
assert new==old
assert before=={str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
assert record['config']['source_run']==cfg['upstream_run']
assert record.get('repos') and record.get('data') and record.get('lineage')
summary=dict(version=flexlock.__version__,library=flexlock.__file__,save_dir=result.save_dir,
 status=str(result.status),scientific_replay=True,training=False,inference=False,
 common_platform_days=new['common_platform_days'],assessment_matches_retained=True,
 old_artifacts_unchanged=True,source_run=record['config']['source_run'],
 source_repositories=list(record['repos']),data=list(record['data']),lineage=list(record['lineage']))
(ROOT/'sst-validation.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
