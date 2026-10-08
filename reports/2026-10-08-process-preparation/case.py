"""Fresh-process full preparation with mocked scheduler and phase accounting."""
import argparse
import json
from pathlib import Path
import resource
import time

from benchmarks.thousand_items import measure
from flexlock import sweep_compile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--producer', action='store_true')
    parser.add_argument('--local', action='store_true')
    parser.add_argument('--provenance', action='store_true')
    args = parser.parse_args()
    diagnostics = {}
    original_compile = sweep_compile.compile_sweep

    def timed_compile(base, sweep, *a, **kw):
        diagnostics['selected_workers'] = sweep_compile._workers(base, sweep)
        cpu_start = time.process_time()
        children_start = resource.getrusage(resource.RUSAGE_CHILDREN)
        start = time.perf_counter()
        result = original_compile(base, sweep, *a, **kw)
        diagnostics['compile_seconds'] = time.perf_counter() - start
        diagnostics['controller_cpu_seconds'] = time.process_time() - cpu_start
        children_end = resource.getrusage(resource.RUSAGE_CHILDREN)
        diagnostics['child_cpu_seconds'] = (children_end.ru_utime + children_end.ru_stime
                                            - children_start.ru_utime - children_start.ru_stime)
        diagnostics['child_peak_rss_kib'] = children_end.ru_maxrss
        return result

    sweep_compile.compile_sweep = timed_compile
    if args.producer:
        from flexlock.run_record import RunRecord
        producer = Path(args.output + '-producer')
        RunRecord(producer).write_lock(dict(config=dict(value=['literal ${missing}', dict(n=41)]), timestamp='fixed'))
        original_config = measure.make_config

        def producer_config(*a, **kw):
            cfg = original_config(*a, **kw)
            cfg.update(upstream=str(producer), value='${run_lock:${upstream},config.value}')
            return cfg
        measure.make_config = producer_config
    measure.run(argparse.Namespace(kind='flexlock-local' if args.local else 'flexlock-slurm',
                                  count=args.count, output=args.output, inputs=args.inputs,
                                  provenance=args.provenance, data=False, cache_search=False,
                                  record='dir', batch=16, profile=False))
    path = Path(args.output)/'measurement.json'
    result = json.loads(path.read_text())
    result['compilation'] = diagnostics
    path.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(output=args.output, **diagnostics)), flush=True)


if __name__ == '__main__':
    main()
