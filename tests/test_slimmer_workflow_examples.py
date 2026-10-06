"""Executable review examples: concrete bindings, coverage gate and launch ledger."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from flexlock.record import load_record
from flexlock.runner import FlexLockRunner
from examples.slimmer_workflows import campaign, orchestrate


def test_multistage_example_reads_exact_predecessors(tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'.flexlock/index.db'))
    FlexLockRunner().run(['-d', 'examples.slimmer_workflows.cfgmod.cfg',
                         '-s', 'prepare', 'train', 'assess', '-o', f'runs_root={tmp_path}', 'run=chain001'])
    root = tmp_path/'baseline/linear/chain001'
    assert json.loads((root/'assess/report.json').read_text()) == {'count': 3, 'total': 12}
    record = load_record(root/'assess')
    assert record['config']['checkpoint_path'] == str(root/'train/model.json')
    assert {entry['path'] for entry in record['lineage'].values()} == {str(root/'prepare'), str(root/'train')}
    # A new run explicitly retains preparation; root overrides do not duplicate it.
    FlexLockRunner().run(['-d', 'examples.slimmer_workflows.cfgmod.cfg', '-s', 'train',
                         '-o', f'runs_root={tmp_path}', 'run=reuse001', f'upstream_run={root}/prepare'])
    assert load_record(tmp_path/'baseline/linear/reuse001/train')['config']['input_path'] == str(root/'prepare/dataset.json')
    assert not (tmp_path/'baseline/linear/reuse001/prepare').exists()


def test_manifest_campaign_checks_empty_excluded_missing_and_corrupt(tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'.flexlock/index.db'))
    rows = []
    for name, values in [('one', [1, 2]), ('empty', [])]:
        source = tmp_path/f'{name}.json'; source.write_text(json.dumps(values))
        rows.append(dict(item_id=name, input_path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(), disposition='process'))
    rows.append(dict(item_id='excluded', disposition='excluded', reason='outside cohort'))
    manifest = tmp_path/'manifest.json';manifest.write_text(json.dumps(rows))
    root = tmp_path/'campaign'; queue = tmp_path/'queue.yaml'
    campaign.export_queue(manifest, root, queue)
    assert len(campaign.check_coverage(manifest, root)['issues']) == 2
    FlexLockRunner().run(['--sweep-file', str(queue), '--sweep-root', str(root), '--n_jobs', '1'])
    report = campaign.check_coverage(manifest, root)
    assert report['produced'] == ['one'] and report['empty'] == ['empty']
    assert report['excluded'] == [{'item_id': 'excluded', 'reason': 'outside cohort'}]
    assert not report['issues']
    (root/'items/one/product.json').write_text('{}')
    assert any('one:' in issue for issue in campaign.check_coverage(manifest, root)['issues'])
    (root/'items/empty/run.complete').unlink()
    assert len(campaign.check_coverage(manifest, root)['issues']) == 2


@pytest.mark.parametrize('fail_train', [False, True])
def test_resource_chain_records_acceptance_and_exact_dependencies(tmp_path, monkeypatch, fail_train):
    import subprocess
    commands = []
    def submit(command, **kwargs):
        commands.append(command)
        if fail_train and len(commands) == 2:
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout=str(100+len(commands))+'\n')
    monkeypatch.setattr(orchestrate.subprocess, 'run', submit)
    ledger = tmp_path/'launches.jsonl'
    args = (str(tmp_path/'runs'), 'question', 'alternative', 'run001', 'cpu.yaml', 'gpu.yaml', str(ledger))
    if fail_train:
        with pytest.raises(subprocess.CalledProcessError):orchestrate.orchestrate(*args)
    else:
        orchestrate.orchestrate(*args)
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(rows) == (1 if fail_train else 3)
    assert '--after' not in commands[0]
    assert commands[1][-2:] == ['--after', '101']
    assert commands[1][commands[1].index('--slurm-config')+1] == 'gpu.yaml'
    assert f'upstream_run={tmp_path}/runs/question/alternative/run001/prepare' in commands[1]
    if not fail_train:
        assert commands[2][-2:] == ['--after', '101:102']
        assert commands[2][commands[2].index('--slurm-config')+1] == 'cpu.yaml'


def test_future_producer_chain_compiles_before_any_worker_runs(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from flexlock.record import list_task_records
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'.flexlock/index.db'))
    monkeypatch.setattr('flexlock.worker.time.sleep', lambda _: None)
    payloads = []
    instances = []
    def make_backend(**params):
        backend = MagicMock()
        def accept(fn, *args, **kwargs):
            payloads.append((fn, args, kwargs))
            return SimpleNamespace(job_id=str(700+len(payloads)))
        backend.submit.side_effect = accept
        instances.append(params)
        return backend
    monkeypatch.setattr('flexlock.parallel.SlurmBackend', make_backend)
    profile = tmp_path/'profile.yaml';profile.write_text('startup_lines: []\n')
    base = ['-d', 'examples.slimmer_workflows.cfgmod.cfg', '-o', f'runs_root={tmp_path}', 'run=future001',
            '--slurm-config', str(profile), '--print-job-id']
    FlexLockRunner().run(base + ['-s', 'prepare'])
    FlexLockRunner().run(base + ['-s', 'train', '--after', '701'])
    FlexLockRunner().run(base + ['-s', 'assess', '--after', '701:702'])
    root = tmp_path/'baseline/linear/future001'
    assert not (root/'prepare/dataset.json').exists()
    task = list_task_records(root/'train/run.lock.tasks.db')[0]['task']
    assert task['input_path'] == '${run_lock:'+str(root/'prepare')+',config.output_path}'
    assert instances[1]['after'] == ['701'] and instances[2]['after'] == ['701', '702']
    # Simulate afterok ordering: the same payloads then execute in dependency order.
    for fn, args, kwargs in payloads:
        fn(*args, **kwargs)
    assert json.loads((root/'assess/report.json').read_text()) == {'count': 3, 'total': 12}
    assert load_record(root/'train')['config']['input_path'] == str(root/'prepare/dataset.json')
    assert 'dataset' in load_record(root/'train')['data']
    assert {'dataset', 'model'} == set(load_record(root/'assess')['data'])
