"""Shared tiny workload; framework lifecycle/metadata costs dominate."""
import hashlib
import json
from pathlib import Path


def run_item(save_dir, item, input_path=None, input_root=None, options=None):
    payload = Path(input_path).read_bytes() if input_path else b''
    result = dict(item=item, sha256=hashlib.sha256(payload).hexdigest())
    root = Path(save_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root/'product.json').write_text(json.dumps(result))
    return result
