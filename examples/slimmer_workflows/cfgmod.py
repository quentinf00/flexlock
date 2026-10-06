"""Root anchors select upstreams; stages contain only their callable arguments."""
from pathlib import Path
from flexlock import py2cfg
from examples.slimmer_workflows.stages import prepare, train, assess

cfg = dict(
    runs_root=str(Path(__file__).resolve().parent / 'runs'),
    track='baseline', arm='linear', run='demo001',
    run_dir='${runs_root}/${track}/${arm}/${run}',
    upstream_run='${run_dir}/prepare',
    training_run='${run_dir}/train',
    prepare=py2cfg(prepare,
        save_dir='${run_dir}/prepare', output_path='${run_dir}/prepare/dataset.json',
        _snapshot_=dict(repos={}),
        _outputs_=dict(dataset=dict(path='dataset.json', sha256=True))),
    train=py2cfg(train,
        save_dir='${run_dir}/train', checkpoint_path='${run_dir}/train/model.json',
        input_path='${run_lock:${upstream_run},config.output_path}', multiplier=2,
        _snapshot_=dict(repos={}, prevs=['${upstream_run}'], data=dict(dataset='${upstream_run}/dataset.json')),
        _outputs_=dict(model=dict(path='model.json', sha256=True))),
    assess=py2cfg(assess,
        save_dir='${run_dir}/assess', report_path='${run_dir}/assess/report.json',
        input_path='${run_lock:${upstream_run},config.output_path}',
        checkpoint_path='${run_lock:${training_run},config.checkpoint_path}',
        _snapshot_=dict(repos={}, prevs=['${upstream_run}', '${training_run}']),
        _outputs_=dict(report=dict(path='report.json', sha256=True))),
)
# Demo declares no repo snapshot. Real projects should declare their code checkout
# and immutable input identities explicitly; see the accompanying guidelines.
