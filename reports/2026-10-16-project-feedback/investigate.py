"""Small local reproductions; no scheduler or scientific project execution."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from git import Repo
from omegaconf import OmegaConf
from flexlock import Project
from flexlock.record import load_record
from flexlock.run_record import RunRecord
from flexlock.outputs import validate_outputs
import flexlock.outputs as outputs
from examples.slimmer_workflows.bindings import require_product

report = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='flexlock-adoption-attribution-') as scratch:
    root = Path(scratch)
    os.environ['FLEXLOCK_INDEX'] = str(root/'index.db')
    repo_path = root/'source';repo_path.mkdir()
    repo = Repo.init(repo_path)
    with repo.config_writer() as writer:
        writer.set_value('user', 'name', 'Validation')
        writer.set_value('user', 'email', 'validation@example.invalid')
    for name in ['a.py', 'b.py']:(repo_path/name).write_text('# synthetic selected source\n')
    repo.index.add(['a.py', 'b.py']);repo.index.commit('fixture')
    stages = [dict(_target_='examples.slimmer_workflows.stages.prepare',
        save_dir=str(root/'runs'/name), output_path=str(root/'runs'/name/'dataset.json'),
        _snapshot_=dict(discover=dict(repos=False),
            repos=dict(main=dict(path=str(repo_path), include=[name+'.py']))))
        for name in ['a', 'b']]
    result = Project().submit_pipeline([[OmegaConf.create(s) for s in stages]], n_jobs=1)
    evidence = {}
    for name in ['a', 'b']:
        record = load_record(root/'runs'/name)
        assert (root/'runs'/name/'run.complete').exists()
        captured = record['repos']['main']
        evidence[name] = dict(declared_include=record['config']['_snapshot_']['repos']['main']['include'],
            captured_include=captured['include'],
            captured_files=repo.git.ls_tree('-r', '--name-only', captured['tree']).splitlines())
        assert evidence[name]['declared_include'] == [name+'.py']
        assert evidence[name]['captured_files'] == ['a.py', 'b.py']
    (report/'composite-attribution.json').write_text(json.dumps(evidence, indent=2)+'\n')

with tempfile.TemporaryDirectory(prefix='flexlock-adoption-hashing-') as scratch:
    root = Path(scratch)
    for name in ['a', 'b']:(root/name).write_bytes(name.encode()*32768)
    cfg = dict(save_dir=str(root), first_path=str(root/'a'), second_path=str(root/'b'),
               _outputs_={name:dict(path=name, sha256=True) for name in ['a','b']})
    RunRecord(root).write_lock(dict(config=cfg));validate_outputs(cfg, completing=True)
    RunRecord(root).mark_complete()
    lock_before = hashlib.sha256((root/'run.lock').read_bytes()).hexdigest()
    calls = []
    original = outputs._digest
    def count(path):
        calls.append(dict(path=Path(path).name, bytes=Path(path).stat().st_size))
        return original(path)
    outputs._digest = count
    try:
        require_product(root, 'first_path', root/'a')
        require_product(root, 'second_path', root/'b')
        successful_calls = list(calls)
        (root/'b').write_bytes(b'changed')
        rejected = False
        try:require_product(root, 'first_path', root/'a')
        except Exception:rejected = True
        assert rejected
        assert lock_before == hashlib.sha256((root/'run.lock').read_bytes()).hexdigest()
    finally:outputs._digest = original
    evidence = dict(two_field_calls=successful_calls,
        total_bytes=sum(x['bytes'] for x in successful_calls),
        unique_product_bytes=65536,
        unchanged_record_does_not_hide_product_mutation=rejected)
    assert len(successful_calls)==4
    (report/'hashing-duplication.json').write_text(json.dumps(evidence, indent=2)+'\n')
print('Confirmed source union in two stage records and repeated helper hashing without weakening mutation checks')
