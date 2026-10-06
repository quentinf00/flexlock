"""Tiny stand-ins for project computations; no scientific validity claimed."""
import hashlib
import json
from pathlib import Path
from examples.slimmer_workflows.bindings import require_product


def prepare(output_path, save_dir):
    Path(output_path).write_text(json.dumps([1, 2, 3]))
    return {'output_path': output_path}


def train(input_path, checkpoint_path, save_dir, producer_record, multiplier=2):
    require_product(producer_record, 'output_path', input_path)
    values = json.loads(Path(input_path).read_text())
    Path(checkpoint_path).write_text(json.dumps({'multiplier': multiplier, 'count': len(values)}))
    return {'checkpoint_path': checkpoint_path}


def assess(input_path, checkpoint_path, report_path, save_dir, dataset_record, model_record):
    require_product(dataset_record, 'output_path', input_path)
    require_product(model_record, 'checkpoint_path', checkpoint_path)
    values = json.loads(Path(input_path).read_text())
    model = json.loads(Path(checkpoint_path).read_text())
    result = {'count': len(values), 'total': sum(values) * model['multiplier']}
    Path(report_path).write_text(json.dumps(result))
    return result


def process(item_id, input_path, expected_sha256, save_dir):
    # Hash and parse the same bytes, so changing a path between separate reads
    # cannot make the identity check describe different input from computation.
    raw = Path(input_path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError(f"Input identity differs from frozen manifest: {input_path}")
    values = json.loads(raw)
    payload = {'item_id': item_id, 'input_sha256': actual,
               'outcome': 'produced' if values else 'empty',
               'count': len(values), 'total': sum(values)}
    Path(save_dir, 'product.json').write_text(json.dumps(payload))
    return payload
