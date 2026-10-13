import json
from pathlib import Path
REPORT=Path(__file__).resolve().parent
rows=json.loads((REPORT/'agents-updates.json').read_text())
core=[r for r in rows if Path(r['project']).name=='flexlock']
if core:
    first=core[0]
    backup=REPORT/'agents-before'/str(Path(first['project']).relative_to('/ontap/user/qfebvre'))/'AGENTS.md'
    assert backup.read_text()==''
    target=Path(first['agents'])
    expected=target.read_text()
    assert expected.strip().startswith('<!-- flexlock-release-compatibility -->')
    assert expected.strip().endswith('<!-- /flexlock-release-compatibility -->')
    target.unlink()
rows=[r for r in rows if r not in core]
(REPORT/'agents-updates.json').write_text(json.dumps(rows,indent=2)+'\n')
(REPORT/'shared-source-preserved.json').write_text(json.dumps(dict(removed_only_new_agent_note=True,source_code_unchanged=True,aliases=[r['agents'] for r in core]),indent=2)+'\n')
print('Preserved shared source; consumer AGENTS paths:',len(rows))
