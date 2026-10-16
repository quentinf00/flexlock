import json

import pytest
from flexlock.outputs import validate_outputs
from flexlock.run_record import RunRecord
from examples.slimmer_workflows.chunk_coverage import check_chunk_coverage


def chunk_fixture(tmp_path, rows):
    directory = tmp_path / 'chunk-a';directory.mkdir()
    path = directory / 'outcomes.json'
    path.write_text(json.dumps(dict(chunk_id='a', items=rows)))
    config = dict(save_dir=str(directory), chunk_id='a', outcomes_path=str(path),
                  _outputs_=dict(outcomes=dict(path='outcomes.json', sha256=True)))
    RunRecord(directory).write_lock(dict(config=config))
    validate_outputs(config, completing=True)
    RunRecord(directory).mark_complete()
    return [dict(chunk_id='a', producer_record=str(directory), items=['one', 'two'])]


def test_non_ok_needs_named_acceptance_and_current_manifest_bytes(tmp_path):
    chunks = chunk_fixture(tmp_path, [dict(item_id='one', outcome='ok'),
                                      dict(item_id='two', outcome='missing_zarr')])
    assert check_chunk_coverage(chunks)['issues']
    report = check_chunk_coverage(chunks, accepted_outcomes=['missing_zarr'])
    assert not report['issues']
    assert report['counts'] == dict(ok=1, missing_zarr=1)
    assert report['accepted_non_ok'][0]['item_id'] == 'two'
    (tmp_path/'chunk-a/outcomes.json').write_text('{}')
    assert check_chunk_coverage(chunks, accepted_outcomes=['missing_zarr'])['issues']


@pytest.mark.parametrize('ids', [['one'], ['one', 'one'], ['one', 'other']])
def test_successful_chunk_cannot_hide_wrong_membership(tmp_path, ids):
    chunks = chunk_fixture(tmp_path, [dict(item_id=i, outcome='ok') for i in ids])
    assert 'member outcome' in check_chunk_coverage(chunks)['issues'][0]


def test_missing_chunk_and_duplicate_frozen_membership_block(tmp_path):
    chunks = chunk_fixture(tmp_path, [dict(item_id=i, outcome='ok') for i in ['one', 'two']])
    (tmp_path/'chunk-a/run.complete').unlink()
    assert check_chunk_coverage(chunks)['issues']
    with pytest.raises(ValueError, match='Duplicate'):
        check_chunk_coverage(chunks + chunks)
