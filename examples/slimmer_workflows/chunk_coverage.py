"""Project gate for per-item outcomes inside chunk outputs, not a core API.

Freeze chunk membership and producer paths before scheduling. Each chunk declares
outcomes.json as a hashed output and records its absolute outcomes_path argument.
The gate checks outcome accounting and the manifest bytes, not each data product.
"""
import json
from collections import Counter
from pathlib import Path

from flexlock.record import load_record
from flexlock.exceptions import FlexLockError
from examples.slimmer_workflows.bindings import require_product


def check_chunk_coverage(frozen_chunks, *, accepted_outcomes=()):
    chunk_ids = [chunk['chunk_id'] for chunk in frozen_chunks]
    members = [item for chunk in frozen_chunks for item in chunk['items']]
    if len(set(chunk_ids)) != len(chunk_ids) or len(set(members)) != len(members):
        raise ValueError('Duplicate chunk or item in frozen membership')
    if any(not Path(chunk['producer_record']).is_absolute() for chunk in frozen_chunks):
        raise ValueError('Freeze absolute producer record paths')
    accepted = set(accepted_outcomes)
    summary = dict(counts={}, accepted_non_ok=[], issues=[])
    counts = Counter()
    for chunk in frozen_chunks:
        chunk_id = chunk['chunk_id']
        directory = Path(chunk['producer_record'])
        try:
            path = require_product(directory, 'outcomes_path', directory / 'outcomes.json')
            record = load_record(directory)
            if record['config']['chunk_id'] != chunk_id:
                raise ValueError('wrong producer chunk identity')
            payload = json.loads(path.read_text())
            if payload['chunk_id'] != chunk_id:
                raise ValueError('wrong output chunk identity')
            actual = Counter(row['item_id'] for row in payload['items'])
            if actual != Counter(chunk['items']):
                raise ValueError('missing, duplicate or unexpected member outcome')
            for row in payload['items']:
                outcome = row['outcome']
                if not isinstance(outcome, str) or not outcome:
                    raise ValueError('outcome must be a nonempty name')
                counts[outcome] += 1
                if outcome != 'ok':
                    if outcome not in accepted:
                        summary['issues'].append(f"{chunk_id}/{row['item_id']}: unaccepted {outcome}")
                    else:
                        summary['accepted_non_ok'].append(dict(chunk_id=chunk_id, **row))
        except (OSError, ValueError, KeyError, TypeError, FlexLockError) as exc:
            summary['issues'].append(f'{chunk_id}: {exc}')
    summary['counts'] = dict(counts)
    return summary
