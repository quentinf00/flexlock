"""A stage declares its scope while preserving the shared campaign capture."""
from copy import deepcopy
from pathlib import Path

from git import Repo
from omegaconf import OmegaConf
import pytest

from flexlock import Project
from flexlock.diff import RunDiff
from flexlock.fingerprint import fingerprint
from flexlock.record import load_record
from flexlock.query import load_run_summary, build_graph, format_summary_md
from flexlock.utils import extract_tracking_info


def repository(path, files):
    path.mkdir()
    repo = Repo.init(path)
    with repo.config_writer() as writer:
        writer.set_value('user', 'name', 'Test')
        writer.set_value('user', 'email', 'test@example.invalid')
    for name, content in files.items():
        (path/name).write_text(content)
    repo.index.add(list(files))
    repo.index.commit('source fixture')
    return repo


def stages(root, main, extra):
    def stage(name, repos):
        return OmegaConf.create(dict(
            _target_='examples.slimmer_workflows.stages.prepare',
            save_dir=str(root/name), output_path=str(root/name/'dataset.json'),
            _snapshot_=dict(discover=dict(repos=False), repos=repos)))
    return [stage('prepare', dict(prep=dict(path=str(main), include=['a.py','b.py'], exclude=['b.py']))),
            stage('train', dict(train=dict(path=str(main), include=['b.py']),
                                prep=dict(path=str(extra), include=['extra.py']))),
            stage('untracked', {})]


@pytest.mark.parametrize('mode', ['dir', 'db'])
def test_pipeline_capture_scope_comparison_and_reporting(tmp_path, monkeypatch, mode):
    monkeypatch.setenv('FLEXLOCK_INDEX', str(tmp_path/'index.db'))
    monkeypatch.setenv('FLEXLOCK_HASH_ENV', '1')
    monkeypatch.setattr('flexlock.worker.random.uniform', lambda *_: 0)
    main = tmp_path/'main';extra = tmp_path/'extra'
    repo = repository(main, {'a.py':'a=1\n', 'b.py':'b=1\n', 'pixi.lock':'main env'})
    repository(extra, {'extra.py':'other=1\n', 'pixi.lock':'extra env'})
    first = stages(tmp_path/'first', main, extra)
    result = Project().submit_pipeline([first], task_record=mode)
    assert all(r.is_success for r in result[0])
    records = [load_record(Path(s.save_dir)) for s in first]
    for cfg, record in zip(first, records):
        declared, data, _ = extract_tracking_info(cfg)
        assert set(record['source_scope']) == set(declared)
        assert record['fingerprint'] == fingerprint(cfg, repos=declared, data=data)
        assert repo.git.ls_tree('-r', '--name-only', record['repos']['prep']['tree']).splitlines() == ['a.py','b.py']
        assert set(record['repos']) == {'prep','prep_repo'}
        from flexlock.snapshot import RunTracker
        tracker = RunTracker(Path(cfg.save_dir))
        tracker.record_env(declared)
        proposed = tracker.finalize(cfg)
        comparison = RunDiff(proposed, record)
        assert comparison.compare_git(), comparison.diffs
        assert comparison.compare_env(), comparison.diffs
        assert record['source_scope'] == proposed['source_scope']
        summary = load_run_summary(cfg.save_dir, downstream=False)
        assert summary['source_scope'] == record['source_scope']
        text = format_summary_md(summary)
        assert 'Captured source trees' in text and 'Effective configured source scope' in text
    graph = build_graph(tmp_path/'first', include_groups=False)
    for cfg, record in zip(first, records):
        node = next(n for n in graph['nodes'] if n['id'] == str(Path(cfg.save_dir).resolve()))
        assert node['source_scope'] == record['source_scope']
        assert node['tree_hashes']['prep'] == record['repos']['prep']['tree']

    # Other stages' files and environments change, while prepare's own scope stays.
    (main/'b.py').write_text('b=2\n')
    (extra/'extra.py').write_text('other=2\n')
    (extra/'pixi.lock').write_text('changed extra env')
    second = stages(tmp_path/'second', main, extra)
    result = Project().submit_pipeline([second], task_record=mode)
    assert all(r.is_success for r in result[0])
    fresh = [load_record(s.save_dir) for s in second]
    assert records[0]['repos']['prep']['tree'] != fresh[0]['repos']['prep']['tree']
    diff = RunDiff(fresh[0], records[0], current_save_dir=second[0].save_dir,
                   target_save_dir=first[0].save_dir)
    assert diff.is_match(), diff.diffs
    assert not RunDiff(fresh[1], records[1]).compare_git()
    assert not RunDiff(fresh[1], records[1]).compare_env()
    assert not RunDiff(fresh[0], records[0], match_include=['b.py'], match_exclude=[]).compare_git()

    # A matching scope declaration is not a substitute for preserved source.
    missing = deepcopy(fresh[0]);missing['repos'] = {}
    assert not RunDiff(missing, missing).compare_git()
    # No claimed stage scope is inferred into a historical record at read time.
    historical = deepcopy(records[0]);historical.pop('source_scope')
    from flexlock.run_record import RunRecord
    old = tmp_path/'historical';old.mkdir();RunRecord(old).write_lock(historical)
    assert 'source_scope' not in load_record(old)


def test_full_scope_does_not_fall_back_to_narrower_target_scope(tmp_path):
    from flexlock.git_utils import create_shadow_snapshot
    repo = repository(tmp_path/'repo', {'a.py':'a=1', 'b.py':'b=1'})
    path = repo.working_tree_dir
    full = create_shadow_snapshot(path)
    narrow = create_shadow_snapshot(path, include=['a.py'])
    full['path'] = narrow['path'] = path
    current = dict(repos=dict(main=full), source_scope=dict(main=dict(path=path, include=[], exclude=[])))
    target = dict(repos=dict(main=narrow), source_scope=dict(main=dict(path=path, include=['a.py'], exclude=[])))
    assert not RunDiff(current, target).compare_git()
    # Comparisons use the proposed/current scope. Here the target preserved it.
    assert RunDiff(target, current).compare_git()


def test_producer_lineage_preserves_recorded_scope(tmp_path):
    from flexlock.run_record import RunRecord
    from flexlock.resolvers import bind_existing_run_locks
    from flexlock.snapshot import snapshot
    producer = tmp_path/'producer';producer.mkdir()
    scope = dict(main=dict(path=str(tmp_path/'source'), include=['src/'], exclude=[]))
    RunRecord(producer).write_lock(dict(config=dict(output_path=str(producer/'data')), source_scope=scope))
    RunRecord(producer).mark_complete()
    cfg = OmegaConf.create(dict(save_dir=str(tmp_path/'consumer'), input_path='${run_lock:'+str(producer)+',config.output_path}'))
    cfg = bind_existing_run_locks(cfg)
    captured = cfg._snapshot_.run_lock_records[str(producer)]
    assert OmegaConf.to_container(captured.source_scope) == scope
    record = snapshot(cfg, return_snapshot=True)
    assert next(iter(record['lineage'].values()))['info']['source_scope'] == scope
    assert record['source_scope'] == {}  # A consumer does not inherit producer declarations.
