import json
from pathlib import Path
from packaging.requirements import Requirement
report=Path('/ontap/user/qfebvre/flexlock-execution-validation/reports/2026-10-12-reader-migration')
rows=json.loads((report/'audit.json').read_text())
requirements=[Requirement(x) for x in ['gitpython>=3.1.46,<4','xxhash>=3.5.0,<4','joblib>=1.5.2,<2','pandas>=2.3.0,<3','omegaconf>=2.3.0,<3','loguru>=0.7.3,<0.8','cloudpickle>=3,<4']]
for row in rows:
 row['dependency_mismatches']=[str(r) for r in requirements if 'dependencies' in row and row['dependencies'][r.name] not in r.specifier]
 row['eligible']=not row['defer'] and 'error' not in row and not row['dependency_mismatches']
(report/'migration-plan.json').write_text(json.dumps(rows,indent=2)+'\n')
print('Eligible:',sum(r['eligible'] for r in rows),'active deferred:',sum(r['defer'] for r in rows),'other deferred:',sum(not r['eligible'] and not r['defer'] for r in rows))
