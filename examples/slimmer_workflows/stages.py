"""Tiny stand-ins for project computations; no scientific validity claimed."""
import json
from pathlib import Path


def prepare(output_path, save_dir):
    Path(output_path).write_text(json.dumps([1, 2, 3]))
    return {'output_path': output_path}


def train(input_path, checkpoint_path, save_dir, multiplier=2):
    values = json.loads(Path(input_path).read_text())
    Path(checkpoint_path).write_text(json.dumps({'multiplier': multiplier, 'count': len(values)}))
    return {'checkpoint_path': checkpoint_path}


def assess(input_path, checkpoint_path, report_path, save_dir):
    values = json.loads(Path(input_path).read_text())
    model = json.loads(Path(checkpoint_path).read_text())
    result = {'count': len(values), 'total': sum(values) * model['multiplier']}
    Path(report_path).write_text(json.dumps(result))
    return result


def process(item_id, input_path, save_dir):
    values = json.loads(Path(input_path).read_text())
    payload = {'item_id': item_id, 'outcome': 'produced' if values else 'empty',
               'count': len(values), 'total': sum(values)}
    Path(save_dir, 'product.json').write_text(json.dumps(payload))
    return payload
