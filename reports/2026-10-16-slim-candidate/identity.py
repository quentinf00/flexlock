"""Verify wheel/package source identity without importing the checkout package."""
import email
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

root=Path(__file__).resolve().parents[2]
report=Path(__file__).resolve().parent
wheel=report/'dist/flexlock-0.10.0rc1-py3-none-any.whl'
installed=Path('/tmp/flexlock-0.10.0rc1-validation/lib/python3.13/site-packages')
files={}
with zipfile.ZipFile(wheel) as archive:
 for name in archive.namelist():
  if not name.startswith('flexlock/') or name.endswith('/'):continue
  data=archive.read(name)
  assert (root/name).read_bytes()==data,name
  assert (installed/name).read_bytes()==data,name
  files[name]=hashlib.sha256(data).hexdigest()
 metadata=email.message_from_bytes(archive.read('flexlock-0.10.0rc1.dist-info/METADATA'))
 assert metadata['Version']=='0.10.0rc1'
result=dict(passed=True,version=metadata['Version'],wheel=str(wheel),
 wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
 source_base=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
 note='Package bytes match this working tree and the isolated installed wheel; base HEAD alone does not identify uncommitted changes.',
 requires_dist=metadata.get_all('Requires-Dist'),package_files=files)
(report/'wheel-identity.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(passed=True,package_files=len(files),wheel_sha256=result['wheel_sha256'])))
