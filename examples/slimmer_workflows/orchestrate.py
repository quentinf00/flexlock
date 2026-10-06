"""Three ordinary CLI launches, explicit producer paths and resource profiles.

Run from the project checkout with the intended environment on PATH. This script
actually submits jobs: it is a template to review, not an automatic acceptance run.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path


def launch(stage, overrides, profile, after=None):
    command = ['flexlock-run', '-d', 'examples.slimmer_workflows.cfgmod.cfg',
               '-s', stage, '-o', *overrides, '--slurm-config', profile, '--print-job-id']
    if after:
        command += ['--after', ':'.join(after)]
    # stderr contains execution diagnostics. stdout is reserved for a scheduler ID.
    result = subprocess.run(command, text=True, check=True, stdout=subprocess.PIPE)
    job_id = result.stdout.strip()
    if not re.fullmatch(r'\d+(?:_\d+)?', job_id):
        raise ValueError(f'Expected a Slurm job ID, received {job_id!r}')
    return {'job_id': job_id, 'command': command}


def orchestrate(runs_root, track, arm, run, cpu_profile, gpu_profile, ledger):
    runs_root = Path(runs_root).resolve()
    root = runs_root / track / arm / run
    anchors = [f'runs_root={runs_root}', f'track={track}', f'arm={arm}', f'run={run}',
               f'upstream_run={root}/prepare', f'training_run={root}/train']
    # Persist each successful submission immediately. If a later launch fails,
    # earlier accepted jobs still exist; inspect the ledger rather than resubmit all.
    with Path(ledger).open('x') as stream:
        prepare = launch('prepare', anchors, cpu_profile)
        stream.write(json.dumps({'stage': 'prepare', 'producer_path': str(root/'prepare'), **prepare})+'\n'); stream.flush()
        train = launch('train', anchors, gpu_profile, after=[prepare['job_id']])
        stream.write(json.dumps({'stage': 'train', 'producer_path': str(root/'train'), **train})+'\n'); stream.flush()
        assess = launch('assess', anchors, cpu_profile, after=[prepare['job_id'], train['job_id']])
        stream.write(json.dumps({'stage': 'assess', 'producer_path': str(root/'assess'), **assess})+'\n'); stream.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ['runs-root', 'track', 'arm', 'run', 'cpu-profile', 'gpu-profile', 'ledger']:
        parser.add_argument('--'+arg, required=True)
    orchestrate(**vars(parser.parse_args()))
