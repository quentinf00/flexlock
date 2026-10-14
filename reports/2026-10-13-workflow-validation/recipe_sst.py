"""Replay the retained SST matchup comparison into a fresh track/arm/run.

Historical save_dir is relative; the selected producer directory is the path
anchor. Do not reinterpret its recorded relative path against today's cwd.
"""
from flexlock import py2cfg
from sst_ml_mapping.workflow_reassessment import reassess

cfg = dict(
    runs_root='/ontap/user/qfebvre/workflow-transition-validation/20261013/runs',
    track='native-vs-legacy', arm='frozen-matchups', run='acceptance-001',
    run_dir='${runs_root}/${track}/${arm}/${run}',
    upstream_run='/ontap/user/qfebvre/work/projects/251218_sst/sst_ml_zarrpatch/results_starter_glob/native_regrid_evaluation_2021',
    assess=py2cfg(reassess,
        save_dir='${run_dir}/assess', source_run='${upstream_run}',
        source_checkout='/ontap/user/qfebvre/work/projects/251218_sst/sst_ml_zarrpatch',
        dates=[f'2021-{m:02d}-15' for m in range(1, 13)],
        products=['t15', 't15_native', 'odyssea'],
        _snapshot_=dict(
            repos=dict(sst='/ontap/user/qfebvre/sst-workflow-pilot',
                       flexlock='/ontap/user/qfebvre/flexlock-execution-validation'),
            prevs=['${...source_run}'],
            data=dict(matchups='${...source_run}/drifters/drifter_matchups.csv')),
        _outputs_=dict(
            matchups=dict(path='paired_matchups.csv', sha256=True),
            provenance=dict(path='provenance.json', sha256=True),
            assessment=dict(path='assessment.json', sha256=True,
                validator=dict(_target_='sst_ml_mapping.workflow_reassessment.validate_assessment')))))
