"""Install the reviewed wheel only in idle, dependency-compatible prefixes.

No source checkout, project manifest, lockfile or non-FlexLock dependency is
changed. Backups are retained for each prefix. Project lock migration remains
a separate step; an ordinary Pixi sync may restore its previous FlexLock.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

REPORT = Path(__file__).resolve().parent
WHEEL = REPORT / 'flexlock-0.9.1-py3-none-any.whl'
BACKUPS = Path('/ontap/user/qfebvre/flexlock-migration-backups-20261012')
UV = '/ontap/user/qfebvre/.local/bin/uv'

PROBE = '''import json, tempfile
from pathlib import Path
import flexlock
from flexlock.taskdb import queue_tasks
from flexlock.destination_guard import reserve_queue, has_active_destination
assert flexlock.__version__ == '0.9.1'
assert '/site-packages/flexlock/' in flexlock.__file__
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    product = root/'product'
    db = root/'run.lock.tasks.db'
    queue_tasks(db, [dict(task_id='probe', save_dir=str(product))])
    reserve_queue([product], db)
    assert not (product/'.flexlock-queue.json').exists()
    assert has_active_destination(product)
print(json.dumps(dict(version=flexlock.__version__, source=flexlock.__file__, active_guard=True)))
'''

def main():
    BACKUPS.mkdir(exist_ok=True)
    rows = json.loads((REPORT/'migration-plan.json').read_text())
    results = []
    for row in rows:
        # A parent project has active jobs; its tools can be imported by them.
        if not row['eligible'] or any(name in row['prefix'] for name in
                                      ('tcwind-benchtools-', 'flexlock-')):
            continue
        prefix = Path(row['prefix'])
        site = Path(row['site'])
        identity = hashlib.sha256(str(prefix).encode()).hexdigest()[:16]
        archive = BACKUPS/(identity+'.tar.gz')
        if archive.exists():
            raise RuntimeError(f'Backup already exists: {archive}; inspect before repeating')
        paths = set(site.glob('flexlock*')) | set(site.glob('*flexlock*.pth'))
        paths.update(p for p in (prefix/'bin').glob('flexlock*') if p.is_file())
        with tarfile.open(archive, 'w:gz') as backup:
            for path in sorted(paths):
                backup.add(path, arcname=str(path.relative_to(prefix)))
        log = REPORT/(identity+'.install.log')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
        env.pop('PYTHONPATH', None)
        with log.open('w') as stream:
            process = subprocess.run([UV, 'pip', 'install', '--offline', '--no-deps',
                '--reinstall-package', 'flexlock', '--python', str(prefix/'bin/python'),
                str(WHEEL)], env=env, cwd='/tmp', stdout=stream,
                stderr=subprocess.STDOUT, timeout=120)
        result = dict(prefix=str(prefix), backup=str(archive), install_exit=process.returncode)
        if process.returncode == 0:
            check = subprocess.run([str(prefix/'bin/python'), '-c', PROBE],
                env=env, cwd='/tmp', text=True, capture_output=True, timeout=60)
            result.update(probe_exit=check.returncode, probe_output=check.stdout,
                          probe_error=check.stderr)
        results.append(result)
        (REPORT/'migration-results.json').write_text(json.dumps(results, indent=2)+'\n')
        print(json.dumps(result), flush=True)
        if process.returncode or result.get('probe_exit'):
            raise RuntimeError(f'Migration check failed for {prefix}; stop and inspect backup/log')

if __name__ == '__main__':
    main()
