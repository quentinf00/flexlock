"""Inventory and counterexample only; no library changes or user artifacts."""
from collections import Counter
import json
from pathlib import Path
import tempfile

from omegaconf import OmegaConf
from flexlock.destination_guard import has_active_destination, guard_destinations
from flexlock.exceptions import FlexLockValidationError
from flexlock.resolvers import bind_existing_run_locks
from flexlock.run_record import RunRecord
from flexlock.taskdb import queue_tasks


def main():
    raw = Path('/ontap/user/qfebvre/flexlock-hydra-benchmark/2026-10-08-compiled-guard-reuse')
    inventory = {}
    for case in ('plain-0-reuse', 'local-100'):
        root = raw/case
        groups = Counter()
        sizes = Counter()
        for path in root.rglob('*'):
            if path.is_file():
                name = path.name
                if path.suffix in ('.pkl', '.slurm'):
                    name = '*'+path.suffix
                groups[name] += 1
                sizes[name] += path.stat().st_size
        inventory[case] = dict(counts=dict(groups), bytes=dict(sizes),
                               measurement=json.loads((root/'measurement.json').read_text()))
    with tempfile.TemporaryDirectory(prefix='flexlock-bookkeeping-') as tmp:
        root = Path(tmp)
        product = root/'queue'/'product'
        db = root/'queue'/'run.lock.tasks.db'
        RunRecord(product).write_lock(dict(config=dict(value='old artifact'), timestamp='old'))
        queue_tasks(db, [dict(save_dir=str(product), value='replacement')])
        assert not has_active_destination(product)
        bound = bind_existing_run_locks(OmegaConf.create(dict(value='${run_lock:'+str(product)+',config.value}')))
        assert bound.value == 'old artifact'
        try:
            with guard_destinations([product]):
                raise AssertionError('ownership guard failed to reject pending work')
        except FlexLockValidationError:
            pass
        inventory['pointerless_nested_counterexample'] = dict(
            pending_queue=True, ownership_guard_rejects=True,
            producer_active_reader=False, submit_binding='old artifact',
            implication='Removing nested pointers without reader migration permits stale binding.')
    out = Path(__file__).with_name('inventory.json')
    out.write_text(json.dumps(inventory, indent=2)+'\n')
    print(json.dumps(inventory, indent=2))


if __name__ == '__main__':
    main()
