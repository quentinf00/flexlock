"""Project-owned SAR outcome proposal; not integrated into SAR extraction.

An extractor must explicitly write this receipt after finishing. A missing CSV
cannot establish an empty outcome. FlexLock can validate the required item.json
through its existing output validator hook.
"""
import csv
import hashlib
import json
from pathlib import Path


def validate_item(path, expected_safe=None):
    """Validate one receipt and its conditional product; return the parsed receipt."""
    path = Path(path)
    item = json.loads(path.read_text())
    if item.get('schema') != 1 or not isinstance(item.get('safe'), str) or not item['safe']:
        raise ValueError('Missing receipt schema or SAFE identity')
    if expected_safe is not None and item['safe'] != expected_safe:
        raise ValueError('Receipt belongs to another SAFE')
    count = item.get('rows')
    if type(count) is not int or count < 0:
        raise ValueError('Rows must be a nonnegative integer')
    if item.get('outcome') == 'empty':
        if count != 0 or not isinstance(item.get('reason'), str) or not item['reason'].strip():
            raise ValueError('Empty outcomes require zero rows and an explicit reason')
        if item.get('product') is not None or item.get('sha256') is not None:
            raise ValueError('Empty outcomes cannot declare a product')
    elif item.get('outcome') == 'produced':
        relative = Path(item.get('product', ''))
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:
            raise ValueError('Product must be a relative path inside the item directory')
        product = (path.parent / relative).resolve()
        if not product.is_relative_to(path.parent.resolve()):
            raise ValueError('Product escapes the item directory')
        if count == 0 or hashlib.sha256(product.read_bytes()).hexdigest() != item.get('sha256'):
            raise ValueError('Missing, empty or changed produced product')
        with product.open(newline='') as stream:
            reader = csv.reader(stream)
            header = next(reader, None)
            observed = sum(1 for _ in reader)
        if not header or observed != count:
            raise ValueError('CSV row count differs from receipt')
    else:
        raise ValueError('Only explicitly produced or empty outcomes are accepted')
    return item
