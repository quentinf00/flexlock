"""Negative acceptance cases for the isolated project outcome proposal."""
import hashlib
import json

import pytest
from examples.slimmer_workflows.sar_outcomes import validate_item


def receipt(tmp_path, **changes):
    product = tmp_path / 'features.csv'
    product.write_text('name,value\nsafe:one,2\n')
    item = dict(schema=1, safe='/inputs/one.SAFE', outcome='produced', rows=1,
                product='features.csv', sha256=hashlib.sha256(product.read_bytes()).hexdigest())
    item.update(changes)
    path = tmp_path / 'item.json'
    path.write_text(json.dumps(item))
    return path


def test_accepts_produced_and_explicit_empty(tmp_path):
    assert validate_item(receipt(tmp_path), '/inputs/one.SAFE')['rows'] == 1
    path = receipt(tmp_path, outcome='empty', rows=0, product=None, sha256=None,
                   reason='No tiles survived the configured extraction filters')
    assert validate_item(path)['outcome'] == 'empty'


def test_existing_output_hook_binds_effective_safe_and_detects_corruption(tmp_path):
    from flexlock.outputs import validate_outputs
    from flexlock.exceptions import FlexLockValidationError
    from omegaconf import OmegaConf

    receipt(tmp_path)
    cfg = OmegaConf.create(dict(safe='/inputs/one.SAFE', save_dir=str(tmp_path),
        _outputs_=dict(item=dict(path='item.json', sha256=True,
            validator=dict(_target_='examples.slimmer_workflows.sar_outcomes.validate_item',
                           expected_safe='${....safe}')))))
    validate_outputs(cfg, completing=True)
    validate_outputs(cfg)
    cfg.safe = '/inputs/another.SAFE'
    with pytest.raises(FlexLockValidationError, match='another SAFE'):
        validate_outputs(cfg)
    cfg.safe = '/inputs/one.SAFE'
    (tmp_path / 'features.csv').write_text('name,value\nchanged,4\n')
    with pytest.raises(FlexLockValidationError, match='changed produced product'):
        validate_outputs(cfg)


@pytest.mark.parametrize('damage', ['missing', 'changed', 'rows', 'wrong_safe',
                                    'escape', 'symlink', 'ambiguous_empty', 'failed'])
def test_refuses_incomplete_or_misleading_outcomes(tmp_path, damage):
    path = receipt(tmp_path)
    if damage == 'missing':
        (tmp_path / 'features.csv').unlink()
    elif damage == 'changed':
        (tmp_path / 'features.csv').write_text('name,value\nother,9\n')
    elif damage == 'symlink':
        outside = tmp_path.parent / (tmp_path.name + '-outside.csv')
        outside.write_text('name,value\nsafe:one,2\n')
        (tmp_path / 'features.csv').unlink()
        (tmp_path / 'features.csv').symlink_to(outside)
    else:
        changes = dict(rows={'rows': 2}, wrong_safe={'safe': '/inputs/other.SAFE'},
                       escape={'product': '../outside.csv'},
                       ambiguous_empty={'outcome': 'empty', 'rows': 0},
                       failed={'outcome': 'failed'})[damage]
        path = receipt(tmp_path, **changes)
    with pytest.raises((ValueError, OSError)):
        validate_item(path, '/inputs/one.SAFE')
