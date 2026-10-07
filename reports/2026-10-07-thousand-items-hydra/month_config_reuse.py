"""Isolated Hydra composition proof; never imports or executes scientific stages.

The month/base node and monthly_catalog resolver are the proposed sweeps.py
replacement. The demo root only supplies enough structure to verify composition.
"""
import ast
import hashlib
import json
from pathlib import Path

from hydra import compose, initialize
from hydra.core.config_store import ConfigStore
from omegaconf import OmegaConf

SOURCE = Path('/scale/user/qfebvre/projects/2508_nextgems/nextgems_tc_tracking/src/nextgems_tc_tracking/confs/sweeps.py')


def monthly_catalog(yearmonth, field):
    year = int(str(yearmonth).split('-')[0])
    experiment = ('IFS_9-FESOM_5-production-hist' if year < 2020
                  else 'IFS_9-FESOM_5-production')
    return ['IFS', experiment, field]


OmegaConf.register_new_resolver('monthly_catalog', monthly_catalog)
month = dict(
    yearmonth='???',
    cat_2d='${monthly_catalog:${.yearmonth},2D_hourly_healpix512}',
    cat_3d='${monthly_catalog:${.yearmonth},3D_hourly_healpix512}',
)
cs = ConfigStore.instance()
cs.store(name='base', node=month, group='month', package='process_month.pp_fn')
cs.store(name='month_reuse_demo', node=dict(
    defaults=['_self_', {'month': 'base'}],
    process_month=dict(pp_fn=dict(zoom=3, outdir='/unused/prepared'),
                       detect_fn=dict(input_file='${..pp_fn.outdir}/${..pp_fn.yearmonth}_zoom_${..pp_fn.zoom}.nc')),
))

# Extract only the pure generator; importing the original module would register
# all 720 configs and transitively import project configuration/scientific code.
tree = ast.parse(SOURCE.read_text())
generator = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='gen_monthly_cfg')
namespace = {}
exec(compile(ast.Module(body=[generator], type_ignores=[]), str(SOURCE), 'exec'), namespace)
expected = list(namespace['gen_monthly_cfg']())
assert len(expected)==720
for item in expected:
    node = OmegaConf.create(month)
    node.yearmonth = item['yearmonth']
    actual = OmegaConf.to_container(node, resolve=True)
    assert actual['yearmonth']==item['yearmonth']
    assert tuple(actual['cat_2d'])==item['cat_2d']
    assert tuple(actual['cat_3d'])==item['cat_3d']

examples=[]
with initialize(version_base='1.3', config_path=None):
    for ym in ['1990-01','2019-12','2020-01','2049-12']:
        cfg=compose(config_name='month_reuse_demo', overrides=[f'process_month.pp_fn.yearmonth={ym}'])
        resolved=OmegaConf.to_container(cfg, resolve=True)['process_month']
        original=next(n for n in expected if n['yearmonth']==ym)
        assert tuple(resolved['pp_fn']['cat_2d'])==original['cat_2d']
        assert tuple(resolved['pp_fn']['cat_3d'])==original['cat_3d']
        assert resolved['detect_fn']['input_file']==f'/unused/prepared/{ym}_zoom_3.nc'
        examples.append(resolved)

print(json.dumps(dict(original_source=str(SOURCE),
    original_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    original_month_count=len(expected), reusable_month_configs=1,
    verified_month_payloads=720, composed_boundaries=examples,
    scientific_tasks_executed=0), indent=2))
