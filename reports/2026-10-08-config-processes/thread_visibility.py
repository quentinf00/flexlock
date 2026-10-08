"""Controlled stub-visibility reproduction against the retained synthetic producer."""
import argparse
import json
import threading
from pathlib import Path
from omegaconf import OmegaConf
from flexlock.resolvers import deferred_stubbed

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--producer',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    entered,release=threading.Event(),threading.Event()
    errors=[]
    def phase():
        try:
            with deferred_stubbed():
                entered.set()
                assert release.wait(5)
        except Exception as exc:
            errors.append(str(exc))
    cfg=OmegaConf.create(dict(value='${run_lock:'+args.producer+',config.value}'))
    thread=threading.Thread(target=phase)
    thread.start()
    try:
        assert entered.wait(5)
        during=OmegaConf.to_container(cfg,resolve=True)['value']
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not errors
    normal=cfg.value
    assert '${run_lock:' in during and normal==99
    Path(args.output).write_text(json.dumps(dict(other_thread_saw_stub=during,
        after_context_saw_real_value=normal,errors=errors),indent=2)+'\n')
