"""Canonical producer identity with compatible unique-name display keys."""
from pathlib import Path

import yaml
from omegaconf import OmegaConf

from flexlock.snapshot import snapshot
from flexlock.load_stage import load_stage_from_path


def record(directory, name, lineage=None):
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'run.lock').write_text(yaml.safe_dump(dict(config=dict(name=name), lineage=lineage or {})))
    return directory


def test_two_same_named_producers_and_aliases_survive_snapshot(tmp_path):
    a = record(tmp_path/'natural/prepare', 'a')
    b = record(tmp_path/'weighted/prepare', 'b')
    alias = tmp_path/'alias';alias.symlink_to(a, target_is_directory=True)
    data = snapshot(OmegaConf.create(dict(save_dir=str(tmp_path/'consumer'))), repos={},
                    prevs=[str(a), str(b), str(alias), str(a/'run.lock')], return_snapshot=True)
    assert set(data['lineage']) == {str(a), str(b)}
    assert {entry['path'] for entry in data['lineage'].values()} == {str(a), str(b)}
    assert {entry['info']['config']['name'] for entry in data['lineage'].values()} == {'a', 'b'}


def test_flatten_keeps_same_named_branches_shared_ancestors_and_cycle(tmp_path):
    base = record(tmp_path/'base', 'base')
    a = record(tmp_path/'natural/train', 'a', dict(base=dict(path=str(base))))
    b = record(tmp_path/'weighted/train', 'b', dict(base=dict(path=str(base))))
    alias = tmp_path/'alias';alias.symlink_to(a, target_is_directory=True)
    consumer = record(tmp_path/'assess', 'consumer', dict(a=dict(path=str(a)), b=dict(path=str(b)), alias=dict(path=str(alias))))
    # A malformed historical cycle must terminate without losing branches.
    record(base, 'base', dict(consumer=dict(path=str(consumer))))
    stages = load_stage_from_path(str(consumer))
    assert set(stages) == {'base', str(a), str(b), 'assess'}
    assert stages[str(a)]['config']['name'] == 'a'
    assert stages[str(b)]['config']['name'] == 'b'
