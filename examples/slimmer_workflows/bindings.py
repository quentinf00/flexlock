"""Project acceptance policy: select explicitly, then validate before consuming."""
import json
from pathlib import Path

from flexlock.record import load_record, read_marker, marker_db, load_task_record
from flexlock.outputs import validate_outputs


def require_product(producer_record, field, selected_path):
    directory = Path(producer_record).resolve()
    record = load_record(directory)
    if not record or not isinstance(record.get('config'), dict):
        raise ValueError(f'No readable producer record: {directory}')
    if not (directory / 'run.complete').exists():
        raise ValueError(f'Producer is not complete: {directory}')
    marker = read_marker(directory)
    if marker:
        row = load_task_record(marker_db(directory, marker), marker['task_id'])
        if not row:
            raise ValueError(f'Producer queue has no authoritative item: {directory}')
        if row['task'].get('_stages_'):
            # A preceding stage can complete while its composite item is still
            # running (or while a later stage fails). Validate this stage's own
            # record/marker/contracts rather than requiring the whole chain.
            stages = row['snapshot'].get('stages', {})
            stage = stages.get(str(directory)) or next(
                (entry for entry in stages.values() if entry.get('record_dir') == str(directory)), None)
            if not stage or stage.get('config') != record['config']:
                raise ValueError(f'No matching authoritative producer stage: {directory}')
        elif row['status'] != 'done':
            raise ValueError(f'Producer queue does not report completion: {directory}')
    config = record['config']
    path = Path(config[field]).resolve()
    if path != Path(selected_path).resolve():
        raise ValueError(f'Selected {field} disagrees with producer {directory}')
    # This recipe requires declared outputs. Legacy producers need a deliberate
    # project adapter; a readable run.lock alone is insufficient acceptance.
    if not config.get('_outputs_'):
        raise ValueError(f'Producer has no declared output contract: {directory}')
    product_dir = config.get('save_dir', str(directory))
    validate_outputs(config, product_dir, record_dir=directory)
    manifest = json.loads((directory / 'run.outputs.json').read_text())
    if str(path) not in {str(Path(entry['path']).resolve()) for entry in manifest['outputs'].values()}:
        raise ValueError(f'{field} is not a declared producer output: {directory}')
    return path
