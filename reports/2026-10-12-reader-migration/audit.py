import concurrent.futures, json, os, subprocess
from pathlib import Path
root=Path('/ontap/user/qfebvre/flexlock-execution-validation')
report=root/'reports/2026-10-12-reader-migration'
rows=json.loads((report/'installations-before.json').read_text())
unique={r['real_site']:r for r in rows}
affected=('biomass','hafs-jepa','maxss-ml','nextgems_tc','sst_ml_mapping')
probe='''import json, flexlock
from flexlock.queue_refs import ancestor_candidates
from flexlock.destination_guard import has_active_destination
import importlib.metadata as m
print(json.dumps(dict(version=flexlock.__version__, source=flexlock.__file__, dependencies={n:m.version(n) for n in ['omegaconf','gitpython','xxhash','cloudpickle','joblib','pandas','loguru']})))'''
def audit(item):
    site,row=item
    prefix=Path(site).parents[2]
    env=dict(os.environ,PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    try:
        process=subprocess.run([str(prefix/'bin/python'),'-c',probe],cwd='/tmp',env=env,text=True,capture_output=True,timeout=45)
        result=json.loads(process.stdout) if process.returncode==0 else dict(error=process.stderr[-2500:])
    except Exception as exc: result=dict(error=str(exc))
    return dict(prefix=str(prefix),site=site,defer=any(s in str(prefix) for s in affected),**result)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(audit,sorted(unique.items())))
(report/'audit.json').write_text(json.dumps(results,indent=2)+'\n')
print('Total:',len(results),'deferred:',sum(r['defer'] for r in results),'import failures:',sum('error' in r for r in results))
for r in results:
    if 'error' in r: print(r['prefix'], r['error'].splitlines()[-1])
