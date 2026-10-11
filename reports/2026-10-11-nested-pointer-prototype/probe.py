"""Reader-compatibility boundary for nested-pointer omission, in scratch only."""
import ast
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
from omegaconf import OmegaConf
from omegaconf.errors import InterpolationResolutionError
import flexlock.destination_guard as guard
from flexlock.exceptions import FlexLockValidationError
from flexlock.resolvers import bind_existing_run_locks
from flexlock.run_record import RunRecord
from flexlock.taskdb import queue_tasks, claim_next_task

source = subprocess.check_output(['git','show','1244e70:flexlock/destination_guard.py'],text=True)
node = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='has_active_destination')
namespace = vars(guard).copy()
exec(compile(ast.get_source_segment(source,node), 'legacy_reader.py','exec'), namespace)
legacy = namespace['has_active_destination']
results = []
for state in ('pending','running'):
    with tempfile.TemporaryDirectory(prefix='flexlock-pointer-probe-') as tmp:
        root=Path(tmp); product=root/'queue/product'; db=root/'queue/run.lock.tasks.db'
        RunRecord(product).write_lock(dict(config=dict(value='old artifact'),timestamp='old'))
        queue_tasks(db,[dict(save_dir=str(product),value='replacement')])
        if state == 'running': claim_next_task(db,'probe')
        cfg=OmegaConf.create(dict(value='${run_lock:'+str(product)+',config.value}'))
        assert guard.has_active_destination(product)
        try:
            bind_existing_run_locks(cfg)
            raise AssertionError('Required binding accepted an active replacement')
        except InterpolationResolutionError as exc:
            assert 'pending/running work' in str(exc)
        future=bind_existing_run_locks(cfg,allow_future=True)
        assert OmegaConf.to_container(future,resolve=False)['value'] == '${run_lock:'+str(product)+',config.value}'
        try:
            with guard.guard_destinations([product]):
                raise AssertionError('Guard accepted an active replacement')
        except FlexLockValidationError:
            pass
        assert not legacy(product)
        with patch.object(guard,'has_active_destination',legacy):
            assert bind_existing_run_locks(cfg).value == 'old artifact'
        # Pointer remains required for external destinations and for old readers.
        guard.reserve_queue([product],db)
        assert legacy(product)
        external=root/'external/product'
        queue_tasks(db,[dict(save_dir=str(external),value='external')])
        guard.reserve_queue([external],db)
        assert guard.has_active_destination(external) and legacy(external)
        results.append(dict(state=state,current_required_binding_rejects=True,
            current_future_binding_exact=True,current_controller_rejects=True,
            legacy_pointerless_binding='old artifact',legacy_with_pointer_rejects=True,
            external_pointer_retained=True))
out=Path(__file__).with_name('compatibility.json')
out.write_text(json.dumps(dict(legacy_revision='1244e70',cases=results,
    default_writer_changed=False,adoption_requires='Updated readers before pointer omission'),indent=2)+'\n')
print(out.read_text())
