"""Real payload execution and scheduler acceptance at the private backend seam."""
import subprocess
import sys
from pathlib import Path

from flexlock.backends.slurm import SlurmBackend


def test_materialized_script_runs_payload_from_another_directory(tmp_path, monkeypatch):
    output = tmp_path / 'result.txt'
    monkeypatch.chdir(tmp_path)
    backend = SlurmBackend(Path('launch folder'), [], python_exe=sys.executable)

    def task(value, *, suffix):
        output.write_text(value + suffix)

    def reject_submission(*args, **kwargs):
        raise AssertionError('materialization must not call the scheduler')

    with monkeypatch.context() as scoped:
        scoped.setattr('flexlock.backends.slurm.subprocess.check_output', reject_submission)
        invocation = backend._materialize(task, 'accepted', suffix=' payload')
    assert invocation.payload_path.is_absolute()
    assert invocation.script_path.is_absolute()
    assert invocation.cwd == tmp_path
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    subprocess.run(['bash', str(invocation.script_path)], cwd=elsewhere, check=True)
    assert output.read_text() == 'accepted payload'


def test_submit_dispatches_materialized_script_exactly_once(tmp_path, monkeypatch):
    calls = []

    def sbatch(argv, *, text):
        calls.append(argv)
        assert argv[0] == 'sbatch'
        script = Path(argv[1])
        assert script.is_absolute() and script.exists()
        assert '#SBATCH --dependency=afterok:123' in script.read_text()
        assert list(tmp_path.glob('*.pkl'))
        return 'Submitted batch job 456\n'

    monkeypatch.setattr('flexlock.backends.slurm.subprocess.check_output', sbatch)
    backend = SlurmBackend(tmp_path, [], after=['123'])
    job = backend.submit(lambda: None)
    assert job.job_id == '456'
    assert len(calls) == 1
