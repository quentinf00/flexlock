"""Regressions reported by the first project adoption pilots."""
import json
import os
from pathlib import Path
import subprocess
import sys
import warnings
from datetime import datetime

import pytest
from omegaconf import OmegaConf

from flexlock.utils import apply_overrides


@pytest.mark.parametrize('literal', ['183_3', '0' * 64, '1' * 64])
def test_identifier_override_warns_and_yaml_quotes_preserve_string(literal):
    cfg = OmegaConf.create({'key': None, 'deferred': '${missing}'})
    with pytest.warns(UserWarning, match='preserve YAML quotes'):
        apply_overrides(cfg, [f'key={literal}'])
    assert isinstance(cfg.key, int)
    with warnings.catch_warnings(record=True) as messages:
        warnings.simplefilter('always')
        apply_overrides(cfg, [f'key="{literal}"'])
        assert cfg.key == literal
        apply_overrides(cfg, ['count=1000', 'mode=true', 'key=${deferred}'])
        assert not messages  # must not evaluate deferred references


def test_numeric_diagnostic_does_not_resolve_later_duplicate_override():
    cfg = OmegaConf.create({})
    with pytest.warns(UserWarning, match='preserve YAML quotes'):
        apply_overrides(cfg, ['nested.key=183_3', 'nested.key=${missing}'])
    assert OmegaConf.to_container(cfg, resolve=False) == {'nested': {'key': '${missing}'}}


def test_module_execution_uses_import_name_in_src_layout(tmp_path):
    """The worker must import the generated target from an unrelated CWD."""
    package = tmp_path / 'checkout/src/demo_adoption'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('')
    module = package / 'launch.py'
    module.write_text('''import json,sys
from flexlock import py2cfg
from omegaconf import OmegaConf

def stage(value="183_3"):
    return value

class Stage:
    def __init__(self, value=41):
        self.value=value

if __name__ == "__main__":
    print(json.dumps([OmegaConf.to_container(py2cfg(stage)), OmegaConf.to_container(py2cfg(Stage))]))
''')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=os.pathsep.join(
        [str(package.parent), str(Path(__file__).resolve().parents[1])]))
    run = subprocess.run([sys.executable, '-m', 'demo_adoption.launch'],
                         cwd=tmp_path / 'checkout', env=env, text=True,
                         capture_output=True, check=True)
    configs = json.loads(run.stdout)
    assert [c['_target_'] for c in configs] == [
        'demo_adoption.launch.stage', 'demo_adoption.launch.Stage']
    elsewhere = tmp_path / 'worker'; elsewhere.mkdir()
    worker = subprocess.run([sys.executable, '-c',
        'import json,sys; from flexlock.utils import instantiate; '
        'a,b=json.loads(sys.argv[1]); assert instantiate(a)=="183_3"; '
        'assert instantiate(b).value==41', json.dumps(configs)],
        cwd=elsewhere, env=env, text=True, capture_output=True)
    assert worker.returncode == 0, worker.stderr


def test_record_timestamps_have_offset_and_parse_as_instants(tmp_path):
    from flexlock.snapshot import RunTracker
    from flexlock.run_record import RunRecord
    record = RunRecord(tmp_path)
    timestamp = RunTracker(tmp_path).data['timestamp']
    parsed = datetime.fromisoformat(timestamp)
    assert parsed.utcoffset() is not None
    assert abs(parsed.timestamp() - datetime.now().timestamp()) < 5
    record.mark_complete()
    assert datetime.fromisoformat(json.loads(record.complete_path.read_text())['ts']).utcoffset() is not None
    record.write_error(ValueError('test'))
    assert datetime.fromisoformat(json.loads(record.error_path.read_text())['timestamp']).utcoffset() is not None


@pytest.mark.parametrize('directive', ['--array=0-3', '--array 0-3', '-a 0-3', '-a0-3'])
def test_slurm_array_workers_have_separate_default_logs(tmp_path, directive):
    from flexlock.backends.slurm import SlurmBackend
    script = SlurmBackend(tmp_path, [f'#SBATCH {directive}']).render_script()
    assert 'slurm-%A_%a.out' in script and 'slurm-%A_%a.err' in script
    custom = SlurmBackend(tmp_path, [f'#SBATCH {directive}', '#SBATCH --output=custom-%a.log'],
                          configure_logging=False).render_script()
    assert 'slurm-%A_%a' not in custom and '--output=custom-%a.log' in custom
    single = SlurmBackend(tmp_path, []).render_script()
    assert '%x-%j.out' in single and '%x-%j.err' in single and '%a' not in single


@pytest.mark.parametrize('flag,key', [('-o', 'main.label'), ('-O', 'label')])
def test_actual_cli_string_quoting_and_warning(tmp_path, flag, key):
    config = tmp_path / 'cfg.yaml'
    config.write_text('main:\n  _target_: builtins.str\n  label: null\n')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    command = [sys.executable, '-m', 'flexlock.run_cli', '-c', str(config),
               '-s', 'main', '--dump', flag]
    unquoted = subprocess.run(command + [f'{key}=183_3'], cwd=tmp_path,
                              env=env, capture_output=True, text=True)
    assert unquoted.returncode == 0, unquoted.stderr
    assert 'preserve YAML quotes' in unquoted.stderr
    assert OmegaConf.create(unquoted.stdout).label == 1833
    quoted = subprocess.run(command + [f'{key}="183_3"'], cwd=tmp_path,
                            env=env, capture_output=True, text=True)
    assert quoted.returncode == 0, quoted.stderr
    assert 'preserve YAML quotes' not in quoted.stderr
    assert OmegaConf.create(quoted.stdout).label == '183_3'


@pytest.mark.parametrize('export', ['dump', 'enqueue'])
def test_exports_keep_selected_merge_and_override_order(tmp_path, capsys, export):
    from flexlock.runner import FlexLockRunner
    import yaml
    config = tmp_path / 'cfg.yaml'
    config.write_text('main:\n  _target_: builtins.str\n  label: old\n  nested:\n    width: 2\n    retained: true\n')
    merge = tmp_path / 'merge.yaml'
    merge.write_text('label: merged\nnested:\n  width: 8\n')
    queue = tmp_path / 'queue.yaml'
    command = ['-c', str(config), '-s', 'main', '-M', str(merge),
               '-O', 'label="183_3"', 'nested.width=16']
    command += ['--dump'] if export == 'dump' else ['--enqueue', str(queue)]
    FlexLockRunner().run(command)
    output = yaml.safe_load(capsys.readouterr().out if export == 'dump' else queue.read_text())
    if export == 'enqueue':
        assert len(output) == 1
        output = output[0]
    assert output['label'] == '183_3'
    assert output['nested'] == dict(width=16, retained=True)
    assert not (tmp_path/'run.lock').exists()
