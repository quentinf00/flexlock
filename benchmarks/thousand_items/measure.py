"""One isolated measurement; dependencies installed outside the shared environment."""
import argparse
from contextlib import contextmanager, ExitStack
import cProfile
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import sqlite3
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def command_guard():
    """Intercept scheduler boundaries, retaining real local Git processes."""
    calls = []
    real_output = subprocess.check_output
    real_popen = subprocess.Popen
    from submitit.core.utils import CommandFunction
    real_command = CommandFunction.__call__

    def fake_output(command, *args, **kwargs):
        binary = Path(command[0]).name if isinstance(command, (list, tuple)) else str(command).split()[0]
        if binary == 'sbatch':
            calls.append(list(command))
            output = 'Submitted batch job 9001\n'
            return output if kwargs.get('text') or kwargs.get('encoding') else output.encode()
        if binary in ('srun', 'squeue', 'sacct', 'scancel', 'qsub'):
            raise AssertionError(f'Scheduler execution forbidden: {command}')
        return real_output(command, *args, **kwargs)

    def guarded_popen(command, *args, **kwargs):
        binary = Path(command[0]).name if isinstance(command, (list, tuple)) else str(command).split()[0]
        if binary in ('sbatch', 'srun', 'squeue', 'sacct', 'scancel', 'qsub'):
            raise AssertionError(f'Unmocked scheduler process forbidden: {command}')
        return real_popen(command, *args, **kwargs)

    def fake_command(self, *args, **kwargs):
        if Path(self.command[0]).name == 'sbatch':
            calls.append(self.command)
            return 'Submitted batch job 9001'
        return real_command(self, *args, **kwargs)

    @contextmanager
    def guarded():
        with ExitStack() as stack:
            stack.enter_context(patch('subprocess.check_output', fake_output))
            stack.enter_context(patch('subprocess.Popen', guarded_popen))
            stack.enter_context(patch.object(CommandFunction, '__call__', fake_command))
            yield
    return calls, guarded()


@contextmanager
def timed(metrics, label):
    before = time.perf_counter()
    try:
        yield
    finally:
        metrics[label] = metrics.get(label, 0) + time.perf_counter() - before


def make_config(destination, inputs, *, provenance=False, data=False):
    from flexlock import py2cfg
    from benchmarks.thousand_items.task import run_item
    snap = dict(discover=dict(repos=False, prevs=False))
    if provenance:
        snap['repos'] = dict(main=dict(path=str(ROOT), include=['benchmarks']))
    if data:
        snap['data'] = dict(input='${...input_path}')
    return py2cfg(run_item, save_dir=str(destination), item=0, input_root=str(inputs),
        input_path='${input_root}/${item}.bin',
        options=dict(seed=42, tags=['file-list', 'cpu'], parameters=list(range(24))), _snapshot_=snap)


def run(args):
    metrics = {}
    case = Path(args.output).resolve()
    case.mkdir(parents=True, exist_ok=False)
    os.environ['FLEXLOCK_INDEX'] = str(case/'index.db')
    os.environ['FLEXLOCK_CACHE'] = str(case/'cache')
    os.environ['FLEXLOCK_CLAIM_BATCH'] = str(args.batch)
    n = args.count
    inputs = Path(args.inputs).resolve()
    destination = case/'runs'
    from omegaconf import OmegaConf
    from flexlock import Project, py2cfg
    import hydra, hydra_zen, submitit
    from benchmarks.thousand_items.task import run_item
    cfg = OmegaConf.create(make_config(destination, inputs, provenance=args.provenance, data=args.data))
    options = OmegaConf.to_container(cfg.options)
    calls, guard = command_guard()
    details = {}
    profile = cProfile.Profile() if args.profile else None
    with guard:
        start = time.perf_counter()
        if profile:profile.enable()
        if args.kind == 'config':
            from hydra_zen import builds, ZenStore
            with timed(metrics, 'py2cfg_generate'):
                flex = [py2cfg(run_item, save_dir=str(destination/i.__str__()), item=i,
                        input_path=str(inputs/f'{i}.bin'), options=options) for i in range(n)]
            with timed(metrics, 'hydra_zen_builds_generate'):
                zen = [builds(run_item, save_dir=str(destination/i.__str__()), item=i,
                        input_path=str(inputs/f'{i}.bin'), options=options, populate_full_signature=True) for i in range(n)]
            store = ZenStore()
            with timed(metrics, 'hydra_zen_deferred_store'):
                for i,node in enumerate(zen):store(node, name=f'job-{i}')
            with timed(metrics, 'hydra_zen_materialize_store'):
                store.add_to_hydra_store()
            with timed(metrics, 'flexlock_omegaconf_materialize'):
                flex = [OmegaConf.create(node) for node in flex]
            details['items'] = len(flex)
        elif args.kind == 'queue':
            from flexlock.taskdb import queue_tasks, claim_next_tasks, finish_tasks, get_status_counts
            tasks = [dict(item=i, input_path=str(inputs/f'{i}.bin'), options=options) for i in range(n)]
            db = case/'tasks.db'
            with timed(metrics, 'queue_serialize_insert'):
                queue_tasks(db, tasks, tag='bench')
            with timed(metrics, 'queue_claim_finish'):
                count = 0
                while batch := claim_next_tasks(db, 'bench', tags=['bench'], n=args.batch):
                    finish_tasks(db, [dict(task=task, result=dict(item=task['item'])) for task in batch])
                    count += len(batch)
            assert count == n and get_status_counts(db).get('done') == n
            details.update(items=count, batch=args.batch)
        elif args.kind in ('flexlock-local', 'flexlock-slurm'):
            from flexlock.worker import time as worker_time
            # Remove randomized cluster-start staggering from framework CPU timing.
            # This does not bypass queue claims, stage execution or provenance.
            with patch.object(worker_time, 'sleep', lambda _: None):
                kw = {}
                if args.kind.endswith('slurm'):
                    slurm = case/'slurm.yaml'
                    slurm.write_text("startup_lines: ['#SBATCH --array=0-3', '#SBATCH --cpus-per-task=1']\n")
                    kw = dict(slurm_config=str(slurm), wait=False)
                with timed(metrics, 'submit_and_run' if not kw else 'prepare_submit'):
                    results = Project().submit(cfg, sweep=[dict(item=i) for i in range(n)],
                        sweep_dir_suffix=True, smart_run=args.cache_search, n_jobs=1,
                        task_record=args.record, **kw)
            assert len(results) == n
            statuses = {str(r.status) for r in results}
            assert statuses == ({'SUBMITTED'} if kw else {'SUCCESS'}), statuses
            with sqlite3.connect(destination/'run.lock.tasks.db') as db:
                rows = db.execute('SELECT status, COUNT(*) FROM tasks GROUP BY status').fetchall()
            details.update(items=n, statuses=rows, scheduler_calls=len(calls))
        elif args.kind in ('hydra-local', 'hydra-slurm'):
            import hydra
            from hydra.core.config_store import ConfigStore
            from hydra.core.hydra_config import HydraConfig
            from hydra.core.utils import JobReturn, JobStatus
            from hydra.utils import instantiate
            from submitit.slurm.slurm import SlurmJob
            node = OmegaConf.to_container(cfg, resolve=False)
            node.pop('_snapshot_')
            node['save_dir'] = '${hydra:runtime.output_dir}'
            ConfigStore.instance().store(name='bench', node=node)
            @hydra.main(version_base='1.3', config_path=None, config_name='bench')
            def app(config):
                return instantiate(config)
            old_argv = sys.argv
            sys.argv = [str(Path(__file__)), '-m', f'item=range(0,{n})',
                        f'hydra.sweep.dir={destination}', 'hydra.sweep.subdir=${hydra.job.num}',
                        'hydra.job.chdir=False', 'hydra/job_logging=disabled', 'hydra/hydra_logging=disabled']
            if args.kind.endswith('slurm'):
                sys.argv += ['hydra/launcher=submitit_slurm', 'hydra.launcher.array_parallelism=4',
                             'hydra.launcher.cpus_per_task=1']
            fake_return = JobReturn();fake_return.status = JobStatus.COMPLETED
            with patch.object(SlurmJob, 'results', lambda self: [fake_return]):
                try:
                    with timed(metrics, 'multirun' if args.kind.endswith('local') else 'prepare_submit'):
                        app()
                finally:
                    sys.argv = old_argv
            details.update(items=n, scheduler_calls=len(calls), mock_results=args.kind.endswith('slurm'))
        elif args.kind == 'identity':
            from flexlock.resolvers import bind_existing_run_locks, resolve_deferred
            from flexlock.run_record import RunRecord
            from flexlock.data_hash import hash_data
            from flexlock.fingerprint import fingerprint
            from flexlock.snapshot import snapshot
            producer = case/'producer'
            RunRecord(producer).write_lock(dict(config=dict(output_path=str(inputs)), timestamp='2026-10-07'))
            refs = OmegaConf.create(dict(input='${run_lock:'+str(producer)+',config.output_path}'))
            with timed(metrics, 'bind_record_per_item'):
                bound = [bind_existing_run_locks(refs) for _ in range(n)]
            with timed(metrics, 'verify_record_per_item'):
                for node in bound:resolve_deferred(node)
            with timed(metrics, 'hash_directory_paths_and_bytes'):
                directory_digest = hash_data(inputs, jobs=1)
            with timed(metrics, 'hash_individual_files'):
                for i in range(n):hash_data(inputs/f'{i}.bin', use_cache=False)
            with timed(metrics, 'source_fingerprint_per_item'):
                for i in range(n):
                    fingerprint(cfg, repos=dict(main=dict(path=str(ROOT), include=['benchmarks'])), data={})
            with timed(metrics, 'source_snapshot_once'):
                snapshot(cfg, repos=dict(main=dict(path=str(ROOT), include=['benchmarks'])), data={}, prevs=[], return_snapshot=True)
            details.update(items=n, directory_digest=directory_digest,
                           directory_files=len(list(inputs.glob('*.bin'))))
        else:raise ValueError(args.kind)
        if profile:profile.disable()
        elapsed = time.perf_counter()-start
    if args.kind.endswith('local'):
        products = list(destination.rglob('product.json'))
        assert len(products)==n, (len(products),n)
        assert sorted(json.loads(p.read_text())['item'] for p in products)==list(range(n))
        details['validated_products']=len(products)
    artifacts = [p for p in case.rglob('*') if p.is_file()]
    result = dict(kind=args.kind, count=n, output=str(case), provenance=args.provenance,
        data=args.data, cache_search=args.cache_search, task_record=args.record,
        seconds=elapsed, phases=metrics, details=details,
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        fixture_file_count=len(list(inputs.glob('*.bin'))), fixture_bytes=sum(p.stat().st_size for p in inputs.glob('*.bin')),
        artifact_files=len(artifacts), artifact_bytes=sum(p.stat().st_size for p in artifacts),
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        python=sys.executable, versions={name:importlib.metadata.version(name) for name in
            ['hydra-core','hydra-zen','hydra-submitit-launcher','submitit','omegaconf']})
    if profile:profile.dump_stats(str(case/'profile.pstats'))
    (case/'measurement.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',required=True)
    parser.add_argument('--count',type=int,default=1000)
    parser.add_argument('--output',required=True)
    parser.add_argument('--inputs',required=True)
    parser.add_argument('--provenance',action='store_true')
    parser.add_argument('--data',action='store_true')
    parser.add_argument('--cache-search',action='store_true')
    parser.add_argument('--record',choices=['dir','db'],default='dir')
    parser.add_argument('--batch',type=int,default=1)
    parser.add_argument('--profile',action='store_true')
    run(parser.parse_args())
