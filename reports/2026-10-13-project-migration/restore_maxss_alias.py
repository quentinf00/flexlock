from pathlib import Path
import json
REPORT=Path(__file__).resolve().parent
rows=json.loads((REPORT/'pin-results.json').read_text())
for row in rows:
 if '/example_maxss/' not in row['manifest']:continue
 root=Path(row['manifest']).parent
 backup=REPORT/'pins-before'/str(root.relative_to('/ontap/user/qfebvre'))
 # Only replace the exact reviewed manifest written by this migration.
 plan=next(r for r in json.loads((REPORT/'pin-plan.json').read_text()) if r['manifest']==row['manifest'])
 assert Path(row['manifest']).read_bytes()==Path(plan['proposed']).read_bytes()
 Path(row['manifest']).write_bytes((backup/Path(row['manifest']).name).read_bytes())
 Path(row['lock']).write_bytes((backup/'pixi.lock').read_bytes())
 row.update(status='restored_excluded_alias',reason='Shares active MaxSS workspace/environment; restored byte-for-byte; no environment install')
(REPORT/'pin-results.json').write_text(json.dumps(rows,indent=2)+'\n')
print('Restored MaxSS alias manifest and lockfile')
