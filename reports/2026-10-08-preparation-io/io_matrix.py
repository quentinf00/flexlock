"""Interleaved fresh-process preparation comparison, with wall-clock phases."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

BASELINE = Path('/tmp/flexlock-prep-io-baseline.py')
PHASE_DRIVER = Path('/tmp/preparation_phase_timers.py')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root')
    parser.add_argument('--output')
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--workers', type=int)
    args = parser.parse_args()
    if args.output:
        from flexlock import destination_guard as guard
        if args.workers == 0:
            spec = importlib.util.spec_from_file_location('flexlock._prep_io_baseline', BASELINE)
            old = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(old)
            guard.guard_destinations = old.guard_destinations
            guard.reserve_queue = old.reserve_queue
        else:
            guard._IO_WORKERS = args.workers
        spec = importlib.util.spec_from_file_location('preparation_phase_timers', PHASE_DRIVER)
        phases = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(phases)
        phases.measure.run(argparse.Namespace(kind='flexlock-slurm', count=args.count,
            output=args.output, inputs=args.inputs, provenance=False, data=False,
            cache_search=False, record='dir', batch=1, profile=False))
        (Path(args.output)/'wall-clock-phases.json').write_text(json.dumps(dict(phases.metrics),indent=2)+'\n')
        return
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=False)
    manifest = dict(source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hostname=os.uname().nodename, python=sys.executable, options=vars(args),
        baseline_guard_revision='6211ef6', baseline_guard_sha256=hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
        driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        phase_driver_sha256=hashlib.sha256(PHASE_DRIVER.read_bytes()).hexdigest(),
        scheduler='mocked only; four task workers, array 0-3', runs=[])
    for rep in range(args.repeat):
        variants = [0,1,2,4]
        variants = variants[rep%4:]+variants[:rep%4]
        for workers in variants:
            label = 'original' if workers == 0 else f'io-{workers}'
            output = root/f'{label}-n{args.count}-r{rep}'
            command = [sys.executable, str(Path(__file__)), '--output', str(output), '--inputs', args.inputs,
                       '--count', str(args.count), '--workers', str(workers)]
            entry=dict(variant=label,repeat=rep,command=command,loadavg=os.getloadavg(),start=time.time())
            print(json.dumps(dict(event='start',variant=label,repeat=rep)),flush=True)
            start=time.perf_counter()
            completed=subprocess.run(command,capture_output=True,text=True,timeout=900)
            entry.update(exit_code=completed.returncode,stdout=completed.stdout,stderr=completed.stderr,
                         process_seconds=time.perf_counter()-start)
            if (output/'measurement.json').exists():
                entry['measurement']=json.loads((output/'measurement.json').read_text())
                entry['wall_clock_phases']=json.loads((output/'wall-clock-phases.json').read_text())
            manifest['runs'].append(entry)
            (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
            print(json.dumps(dict(event='finish',variant=label,repeat=rep,exit_code=completed.returncode,
                                 seconds=entry.get('measurement',{}).get('seconds'))),flush=True)
            if completed.returncode:raise SystemExit(completed.returncode)

if __name__=='__main__':main()
