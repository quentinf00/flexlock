"""Investigation only: spawned batch compilation, no queue or scheduler writes."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import time

from omegaconf import OmegaConf
from flexlock.freeze import _freeze_and_bind
from flexlock.presets import freeze_run_refs, validate_chained_paths
from flexlock.utils import merge_task_into_cfg
from benchmarks.thousand_items.measure import make_config

_BASE = None
_AFTER = False

def offset(value):
    return int(value)+7

def initialize(base, after, custom=False):
    global _BASE, _AFTER
    _BASE, _AFTER = OmegaConf.create(base), after
    if custom:
        OmegaConf.register_new_resolver('offset', offset, replace=True)

def compile_batch(indices):
    result=[]
    for item in indices:
        cfg=merge_task_into_cfg(_BASE, dict(item=item), None)
        freeze_run_refs(cfg,defer_unpinned=_AFTER)
        if _AFTER:validate_chained_paths(cfg)
        cfg=_freeze_and_bind(cfg,allow_future=_AFTER)
        result.append(OmegaConf.to_container(cfg,resolve=False))
    return result

def compile_all(base,n,workers,batch,after=False,custom=False):
    chunks=[list(range(i,min(i+batch,n))) for i in range(0,n,batch)]
    start=time.perf_counter()
    if workers==1:
        initialize(base,after,custom)
        result=[item for chunk in chunks for item in compile_batch(chunk)]
    else:
        with ProcessPoolExecutor(max_workers=workers,mp_context=mp.get_context('spawn'),
            initializer=initialize,initargs=(base,after,custom)) as pool:
            result=[item for compiled in pool.map(compile_batch,chunks) for item in compiled]
    return result,time.perf_counter()-start

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--inputs',required=True)
    parser.add_argument('--count',type=int,default=1000)
    parser.add_argument('--repeat',type=int,default=3)
    parser.add_argument('--batch',type=int,default=50)
    args=parser.parse_args()
    root=Path(args.output);root.mkdir(parents=True,exist_ok=False)
    from flexlock.run_record import RunRecord
    producer=root/'producer';producer.mkdir()
    RunRecord(producer).write_lock(dict(config=dict(value=['literal ${missing}',dict(n=41)]),timestamp='fixed'))
    plain=make_config(root/'runs',Path(args.inputs))
    bound=dict(plain,upstream=str(producer),value='${run_lock:${upstream},config.value}')
    cases={'plain':plain,'producer':bound}
    report=dict(source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hostname=os.uname().nodename,affinity_cpus=len(os.sched_getaffinity(0)),options=vars(args),
        driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runs=[])
    references={}
    for rep in range(args.repeat):
        order=[1,2,4];order=order[rep%3:]+order[:rep%3]
        for case,base in cases.items():
            for workers in order:
                print(json.dumps(dict(event='start',case=case,repeat=rep,workers=workers)),flush=True)
                results,seconds=compile_all(base,args.count,workers,args.batch)
                assert [r['item'] for r in results]==list(range(args.count))
                if case not in references:references[case]=results
                assert results==references[case]
                encoded=json.dumps(results,sort_keys=True).encode()
                row=dict(case=case,repeat=rep,workers=workers,seconds=seconds,
                    payload_sha256=hashlib.sha256(encoded).hexdigest(),json_bytes=len(encoded),
                    producer_reads=sum(len(r.get('_snapshot_',{}).get('run_lock_reads',[])) for r in results))
                report['runs'].append(row)
                (root/'results.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(dict(event='finish',**row)),flush=True)
    # Parent-only registration is deliberately not replicated in spawned children.
    custom=dict(plain,value='${offset:${item}}')
    OmegaConf.register_new_resolver('offset',offset,replace=True)
    expected,_=compile_all(custom,8,1,4)
    try:
        compile_all(custom,8,2,4)
    except Exception as exc:
        report['custom_resolver_without_initializer']=dict(error=type(exc).__name__,message=str(exc))
    else:raise AssertionError('spawn unexpectedly inherited parent-only resolver')
    actual,seconds=compile_all(custom,8,2,4,custom=True)
    assert actual==expected
    report['custom_resolver_explicit_initializer']=dict(equivalent=True,seconds=seconds)
    # Promised producers remain exact deferred references, not chosen replacements.
    future=dict(plain,upstream=str(root/'future'),value='${run_lock:${upstream},config.value}')
    expected,_=compile_all(future,8,1,4,after=True)
    actual,_=compile_all(future,8,2,4,after=True)
    assert actual==expected
    report['future_producer']=dict(equivalent=True,path=str(root/'future'))
    # Submit bindings made by children still reject a later producer replacement.
    RunRecord(producer).write_lock(dict(config=dict(value=99),timestamp='changed'))
    from flexlock.resolvers import resolve_deferred
    from flexlock.exceptions import FlexLockValidationError
    try:resolve_deferred(OmegaConf.create(references['producer'][0]))
    except FlexLockValidationError:
        report['changed_producer_rejected']=True
    else:raise AssertionError('producer replacement was not rejected')
    (root/'results.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
