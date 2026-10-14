"""Automatic reuse loads the producer chosen by its single policy lookup."""

import pytest
from omegaconf import OmegaConf

from flexlock.api import Project
from flexlock.run_record import RunRecord


@pytest.mark.parametrize("sweep", [False, True])
def test_cache_hit_keeps_selected_producer_and_comparison_filters(tmp_path, monkeypatch, sweep):
    selected = tmp_path / "producer-A"
    other = tmp_path / "producer-B"
    for path, value in [(selected, "A"), (other, "B")]:
        record = RunRecord(path)
        record.write_lock({"config": {"save_dir": str(path)}})
        record.write_results({"producer": value})
        record.mark_complete(result={"producer": value})

    project = Project()
    calls = []

    def lookup(cfg, search_dirs=None, match_include=None, match_exclude=None):
        calls.append((search_dirs, match_include, match_exclude))
        # A second lookup would choose B and discard the comparison filters.
        return selected if len(calls) == 1 else other

    monkeypatch.setattr(project, "_find_matching_run", lookup)
    cfg = OmegaConf.create({"_target_": "builtins.dict", "save_dir": str(tmp_path / "fresh")})
    results = project.submit(
        cfg, smart_run=True, search_dirs=[str(tmp_path)],
        match_include=["src/stage.py"], match_exclude=["tests/**"],
        sweep=[{}] if sweep else None,
    )
    result = results[0] if sweep else results
    assert calls == [([str(tmp_path)], ["src/stage.py"], ["tests/**"])]
    assert result.status == "CACHED"
    assert result.record_dir == str(selected)
    assert result.save_dir == str(selected)
    assert result.result == {"producer": "A"}
    assert not (tmp_path / "fresh" / "run.lock").exists()
