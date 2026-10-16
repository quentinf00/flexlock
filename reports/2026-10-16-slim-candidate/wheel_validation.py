"""Installed-wheel validation, executed from a directory outside the checkout."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import flexlock
from flexlock import Project
from flexlock.exceptions import FlexLockValidationError
from flexlock.record import load_record
from omegaconf import OmegaConf


def produce(save_dir, value=1, input_path=None, output_path=None):
    if input_path:
        value += json.loads(Path(input_path).read_text())['value']
    product = Path(output_path or Path(save_dir)/'product.json')
    product.write_text(json.dumps({'value': value}))
    return {'value': value}


def cfg(path, value=1):
    return OmegaConf.create(dict(_target_='wheel_validation.produce',
        save_dir=str(path), output_path=str(path/'product.json'), value=value,
        _snapshot_=dict(repos={}, discover=dict(repos=False, prevs=False)),
        _outputs_=dict(product=dict(path='product.json', sha256=True))))


def main():
    assert flexlock.__version__ == importlib.metadata.version('flexlock') == '0.10.0rc1'
    assert Path(flexlock.__file__).is_relative_to(Path(sys.prefix))
    root = Path(tempfile.mkdtemp(prefix='flexlock-wheel-products-'))
    producer = cfg(root/'producer', 2)
    first = Project().submit(producer)
    assert first.status == 'SUCCESS'
    selected = Project().submit(producer, save_dir_policy='skip')
    assert selected.status == 'CACHED' and selected.result == {'value': 2}
    consumer = cfg(root/'consumer', 3)
    consumer.input_path = '${run_lock:' + str(root/'producer') + ',config.output_path}'
    config_file = root/'consumer.yaml';config_file.write_text(OmegaConf.to_yaml(consumer))
    subprocess.run([str(Path(sys.executable).parent/'flexlock-run'), '-c', str(config_file)], check=True)
    record = load_record(root/'consumer')
    assert record['result'] == {'value': 5}
    assert str(root/'producer') in {entry['path'] for entry in record['lineage'].values()}
    unchanged = (root/'producer/run.lock').read_bytes()
    rejected = subprocess.run([str(Path(sys.executable).parent/'flexlock-run'), '-c', str(config_file),
                              '--check-exists'], capture_output=True, text=True)
    assert rejected.returncode != 0
    for key in ['smart_run', 'search_dirs']:
        try:
            Project().submit(cfg(root/'obsolete'), **{key: False})
        except TypeError:
            pass
        else:
            raise AssertionError('retired argument accepted')
    assert not (root/'obsolete').exists()
    try:
        Project().submit(producer)
    except FlexLockValidationError:
        pass
    else:
        raise AssertionError('occupied producer accepted')
    assert (root/'producer/run.lock').read_bytes() == unchanged
    queue_cfg = cfg(root/'items/default')
    items = [dict(value=i, save_dir=str(root/f'items/{i}'),
                  output_path=str(root/f'items/{i}/product.json')) for i in range(4)]
    results = Project().submit(queue_cfg, sweep=items, sweep_root=str(root/'queue'))
    markers = [(Path(r.record_dir)/'run.complete').read_bytes() for r in results]
    continued = Project().submit(queue_cfg, sweep=items, sweep_root=str(root/'queue'))
    assert [r.get('value') for r in continued] == list(range(4))
    assert markers == [(Path(r.record_dir)/'run.complete').read_bytes() for r in continued]
    (root/'producer/product.json').write_text('{}')
    try:
        Project().submit(producer, save_dir_policy='skip')
    except FlexLockValidationError:
        pass
    else:
        raise AssertionError('corrupt selected producer accepted')
    report = dict(passed=True, version=flexlock.__version__, module=flexlock.__file__,
        python=sys.executable, products=str(root), cli_retired_flag_exit=rejected.returncode,
        assertions=['fresh execution', 'CLI consumer and exact lineage', 'record return value',
                    'explicit reuse', 'collision preservation', 'retired keyword/flag rejection',
                    'unchanged queue done-row preservation', 'corrupt output rejection'])
    print(json.dumps(report))


if __name__ == '__main__':
    main()
