"""Sequential fresh-process measurements; append evidence after every completed case."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--counts', default='100,1000')
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--variants', default='config,queue-1,queue-16,hydra-slurm,flexlock-slurm,hydra-local,flexlock-local')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    manifest = dict(python=sys.executable, source_revision=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
        hostname=os.uname().nodename, inputs=args.inputs, options=vars(args),
        scheduler='mocked sbatch; unmocked scheduler subprocesses forbidden',
        runs=[])
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    failures = 0
    for n in map(int,args.counts.split(',')):
        for rep in range(args.repeat):
            variants=args.variants.split(',')
            # Rotate order to reduce systematic first/last effects.
            variants=variants[rep%len(variants):]+variants[:rep%len(variants)]
            for variant in variants:
                kind=variant
                extra=[]
                if variant.startswith('queue-'):
                    kind='queue';extra=['--batch',variant.split('-')[1]]
                elif variant == 'flexlock-local-db':kind='flexlock-local';extra=['--record','db']
                elif variant == 'flexlock-local-source':kind='flexlock-local';extra=['--provenance','--data']
                elif variant == 'flexlock-slurm-source':kind='flexlock-slurm';extra=['--provenance']
                elif variant == 'flexlock-slurm-cache':kind='flexlock-slurm';extra=['--cache-search']
                path=root/f'{variant}-n{n}-r{rep}'
                command=[sys.executable,'-m','benchmarks.thousand_items.measure', '--kind',kind,
                    '--count',str(n),'--output',str(path),'--inputs',args.inputs,*extra]
                if args.profile:command.append('--profile')
                entry=dict(variant=variant,count=n,repeat=rep,command=command,start=time.time(),loadavg=os.getloadavg())
                before=time.perf_counter()
                print(json.dumps(dict(event='start',variant=variant,count=n,repeat=rep)),flush=True)
                try:
                    completed=subprocess.run(command,capture_output=True,text=True,timeout=args.timeout)
                    entry['exit_code']=completed.returncode
                    entry['stdout']=completed.stdout
                    entry['stderr']=completed.stderr
                except subprocess.TimeoutExpired as exc:
                    entry.update(exit_code=124,stdout=str(exc.stdout or ''),stderr=str(exc.stderr or ''),timeout=True)
                entry['process_seconds']=time.perf_counter()-before
                if (path/'measurement.json').exists():
                    entry['measurement']=json.loads((path/'measurement.json').read_text())
                failures+=entry['exit_code']!=0
                manifest['runs'].append(entry)
                (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
                print(json.dumps(dict(event='finish',variant=variant,count=n,repeat=rep,
                    exit_code=entry['exit_code'],seconds=entry.get('measurement',{}).get('seconds'),
                    process_seconds=entry['process_seconds'])),flush=True)
    raise SystemExit(1 if failures else 0)


if __name__=='__main__':main()
