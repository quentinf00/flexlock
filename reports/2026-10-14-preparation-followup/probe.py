"""Bounded CPU hashing and output integrity diagnosis; no jobs or projects."""
import hashlib
import json
import os
from pathlib import Path
import statistics
import tempfile
import time

from omegaconf import OmegaConf
from flexlock.exceptions import FlexLockValidationError
from flexlock.outputs import validate_outputs
from flexlock.taskdb import _hash_task


def main():
    configs = [OmegaConf.create({
        '_target_': 'example.process', 'save_dir': f'/tmp/example/{i}',
        'input_path': f'/tmp/inputs/{i}.bin', 'item_id': i,
        '_snapshot_': {'data': {'input': f'/tmp/inputs/{i}.bin'}},
    }) for i in range(1000)]
    samples = []
    for _ in range(3):
        start = time.perf_counter()
        for _ in range(5):
            ids = [_hash_task(cfg) for cfg in configs]
        samples.append(time.perf_counter() - start)
    assert len(set(ids)) == 1000
    with tempfile.TemporaryDirectory(prefix='flexlock-integrity-probe-') as root:
        run = Path(root)
        product = run / 'product.bin'
        product.write_bytes(b'original')
        cfg = OmegaConf.create({'save_dir': root,
            '_outputs_': {'product': {'path': 'product.bin', 'sha256': True}}})
        validate_outputs(cfg, completing=True)
        validate_outputs(cfg)
        record = run / 'run.lock'
        record.write_text('config: unchanged\n')
        before = hashlib.sha256(record.read_bytes()).hexdigest()
        stat = product.stat()
        product.write_bytes(b'mutated!')  # Same size; restore mtime too.
        os.utime(product, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        after = hashlib.sha256(record.read_bytes()).hexdigest()
        try:
            validate_outputs(cfg)
        except FlexLockValidationError:
            detected = True
        else:
            detected = False
        assert before == after and detected
        assert product.stat().st_size == stat.st_size
        assert product.stat().st_mtime_ns == stat.st_mtime_ns
    print(json.dumps({'hash_calls_per_sample': 5000, 'samples_seconds': samples,
        'median_seconds': statistics.median(samples),
        'record_digest_unchanged_after_corruption': before == after,
        'same_size_and_mtime_corruption_detected': detected,
        'scope': 'synthetic 1000 small DictConfigs; no queue/filesystem throughput claim'}, indent=2))


if __name__ == '__main__':
    main()
