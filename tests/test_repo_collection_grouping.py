"""Controller source grouping must preserve item-dependent repository settings."""
from omegaconf import OmegaConf
import pytest
from flexlock.utils import collect_task_repos


def trace_merges(monkeypatch):
    import flexlock.utils as utils
    calls = []
    original = utils.merge_task_into_cfg
    def traced(*args, **kwargs):
        calls.append(args[1])
        return original(*args, **kwargs)
    monkeypatch.setattr(utils, 'merge_task_into_cfg', traced)
    return calls


@pytest.mark.parametrize('plain', [False, True])
def test_distinct_input_paths_share_literal_source_settings(tmp_path, monkeypatch, plain):
    calls = trace_merges(monkeypatch)
    tasks = [dict(save_dir=str(tmp_path/f'item-{i}'), _snapshot_=dict(
        repos=dict(main=dict(path=str(tmp_path), include=['src'])),
        discover=dict(repos=False, prevs=False), data=dict(input=f'/input/{i}'),
        prevs=[f'/producer/{i}'])) for i in range(10)]
    nodes = tasks if plain else [OmegaConf.create(t) for t in tasks]
    before = [OmegaConf.to_container(t, resolve=False) if OmegaConf.is_config(t) else t.copy() for t in nodes]
    repos = collect_task_repos(OmegaConf.create(dict(save_dir=str(tmp_path/'queue'))), nodes)
    assert repos['main']['path'] == str(tmp_path)
    assert repos['main']['include'] == ['src']
    assert len(calls) == 1
    assert [OmegaConf.to_container(t, resolve=False) if OmegaConf.is_config(t) else t for t in nodes] == before


def test_repository_interpolation_through_data_retains_full_grouping(tmp_path, monkeypatch):
    calls = trace_merges(monkeypatch)
    tasks = [OmegaConf.create(dict(_snapshot_=dict(
        repos=dict(main=dict(path='${_snapshot_.data.repo}')),
        discover=dict(repos=False, prevs=False), data=dict(repo=str(tmp_path/f'repo{i}')))))
        for i in range(2)]
    repos = collect_task_repos(OmegaConf.create(dict(save_dir=str(tmp_path/'queue'))), tasks)
    # Existing first-name-wins behavior remains, but neither item is skipped
    # based on equal interpolation text with different referenced inputs.
    assert repos['main']['path'] == str(tmp_path/'repo0')
    assert len(calls) == 2


def test_partial_target_and_composite_sources(tmp_path, monkeypatch):
    calls = trace_merges(monkeypatch)
    base = OmegaConf.create(dict(save_dir=str(tmp_path/'queue')))
    def stage(name):
        return dict(_snapshot_=dict(repos={name: str(tmp_path/name)},
                                    discover=dict(repos=False, prevs=False)))
    tasks = [dict(main=stage('partial'))]
    assert set(collect_task_repos(base, tasks, 'main')) == {'partial'}
    assert set(collect_task_repos(base, [dict(_stages_=[stage('a'), stage('b')])])) == {'a', 'b'}
    assert len(calls) == 3


def test_different_literal_repositories_and_inherited_defaults(tmp_path, monkeypatch):
    calls = trace_merges(monkeypatch)
    base = OmegaConf.create(dict(save_dir=str(tmp_path/'queue'), _snapshot_=dict(
        repos=dict(base=str(tmp_path/'base')), discover=dict(repos=False, prevs=False))))
    tasks = [dict(_snapshot_=dict(repos={f'repo{i}': str(tmp_path/f'repo{i}')},
                                 data=dict(input=f'/input/{i}'))) for i in range(2)]
    repos = collect_task_repos(base, tasks)
    assert set(repos) == {'base', 'repo0', 'repo1'}
    assert len(calls) == 2
