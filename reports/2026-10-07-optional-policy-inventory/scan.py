"""Read-only, bounded source inventory. Run from the FlexLock checkout root."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path.cwd()
SCOPES = {
    'library': ROOT,
    'lab': Path('/ontap/user/qfebvre/flexlock-workflow-lab'),
    'sar-original': Path('/ontap/user/qfebvre/work/projects/2509_sar_ml/sar-ml-enhanced'),
    'sar-pilot': Path('/ontap/user/qfebvre/sar-ml-workflow-pilot'),
    'sst-original': Path('/ontap/user/qfebvre/work/projects/251218_sst/sst_ml_zarrpatch'),
    'sst-pilot': Path('/ontap/user/qfebvre/sst-workflow-pilot'),
    'sample-project': Path('/scale/user/qfebvre/projects/2509_flexlock/sample_project'),
    'tutorial-project': Path('/scale/user/qfebvre/projects/2509_flexlock/my_awesome_project'),
    'project-template': Path('/scale/user/qfebvre/projects/2509_flexlock/project_template'),
    'zendag': Path('/scale/user/qfebvre/projects/2509_flexlock/zendag'),
}
PATTERN = re.compile(r'smart_run|check-exists|submit_chained|ChainedResult|_skip_complete_|submit_pipeline|run_stage|\$\{run:|\$\{latest:|ParallelExecutor|save_dir_policy.*skip')
GLOBS = ['*.py', '*.sh', '*.yaml', '*.yml', '*.toml', '!**/reports/**', '!**/outputs/**',
         '!**/results*/**', '!**/evidence/**', '!**/workflow-results/**', '!**/.pixi/**',
         '!**/node_modules/**', '!**/.git/**']


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def scan():
    result = {'source_revision': git(ROOT, 'rev-parse', 'HEAD'), 'glob_selection': GLOBS,
              'method': 'rg file selection; lexical matches; AST candidate calls, not runtime reachability',
              'limits': 'Git ignore rules apply; notebooks/IPython, generated outputs, installed packages and other projects are not exhaustively scanned.',
              'scopes': {}}
    for label, root in SCOPES.items():
        entry = {'root': str(root), 'head': git(root, 'rev-parse', 'HEAD'),
                 'dirty_status': git(root, 'status', '--porcelain'), 'matches': [], 'candidate_calls': [],
                 'files': {}, 'parse_errors': []}
        cmd = ['rg', '--files']
        for glob in GLOBS:
            cmd.extend(['-g', glob])
        listing = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=True)
        names = sorted(listing.stdout.splitlines())
        entry['selected_file_count'] = len(names)
        for name in names:
            data = (root/name).read_bytes()
            entry['files'][name] = hashlib.sha256(data).hexdigest()
            text = data.decode('utf-8', errors='replace')
            for line, value in enumerate(text.splitlines(), 1):
                if PATTERN.search(value):
                    entry['matches'].append({'file': name, 'line': line, 'text': value.strip()})
            if not name.endswith('.py'):
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError as exc:
                entry['parse_errors'].append({'file': name, 'line': exc.lineno, 'reason': exc.msg})
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function = ast.unparse(node.func)
                if function.split('.')[-1] not in ('submit', 'submit_pipeline', 'submit_chained', 'run_stage', 'ParallelExecutor'):
                    continue
                keyword = next((k.value for k in node.keywords if k.arg == 'smart_run'), None)
                entry['candidate_calls'].append({'file': name, 'line': node.lineno, 'function': function,
                    'smart_run': ast.unparse(keyword) if keyword is not None else 'omitted',
                    'expanded_kwargs': any(k.arg is None for k in node.keywords)})
        result['scopes'][label] = entry
    return result


if __name__ == '__main__':
    result = scan()
    destination = ROOT/'reports/2026-10-07-optional-policy-inventory/inventory.json'
    destination.write_text(json.dumps(result, indent=2)+'\n')
    for label, entry in result['scopes'].items():
        chained = [m for m in entry['candidate_calls'] if m['function'].endswith('submit_chained')]
        print(label, 'files=',entry['selected_file_count'], 'policy-lines=',len(entry['matches']),
              'call-candidates=',len(entry['candidate_calls']), 'chained-candidates=',len(chained),
              'parse-errors=',len(entry['parse_errors']))
