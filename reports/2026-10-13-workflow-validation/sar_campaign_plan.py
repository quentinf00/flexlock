"""Freeze real SAR listing membership and preview per-item config bindings.

Queue review only: no source hashing/extraction, scientific output or submission.
Missing inputs remain reported; they are not silently excluded from the cohort.
"""
import csv,hashlib,json
from pathlib import Path
from omegaconf import OmegaConf
from flexlock import Project,py2cfg
from flexlock.sweep_compile import compile_sweep
from sar_ml.stages.data import extract_features
from recipe_sar import cfg
ROOT=Path(__file__).resolve().parent
listing=Path(cfg['listing_path'])
with listing.open() as f:rows=list(csv.DictReader(f))
key=next(iter(rows[0]))
identifiers=[Path(row[key]).stem for row in rows]
assert len(identifiers)==len(set(identifiers))
manifest=[dict(item_id=i,input_path=row[key],eligible_train=row['avail_train'],eligible_test=row['avail_test']) for i,row in zip(identifiers,rows)]
(ROOT/'sar-membership.json').write_text(json.dumps(dict(listing_sha256=hashlib.sha256(listing.read_bytes()).hexdigest(),items=manifest),indent=2)+'\n')
# Preview only a named first-three cohort; full membership is retained separately.
selected=manifest[:3]
base=OmegaConf.create(dict(item_id=None,safe=None,
 items_root=str(ROOT/'runs/sar-data/extraction-preview/items'),
 extract=py2cfg(extract_features,safe='${safe}',save_dir='${items_root}/${item_id}',
  _snapshot_=dict(data=dict(safe='${...safe}')))))
compiled=compile_sweep(base,[dict(item_id=r['item_id'],safe=r['input_path']) for r in selected])
items=[(index,Project(defaults=root).get('extract')) for index,root in compiled]
assert all('item_id' not in item for _,item in items)
paths=[str(item.save_dir) for _,item in items]
assert len(paths)==len(set(paths))
summary=dict(cohort_size=len(manifest),preview_size=len(selected),distinct_destinations=True,
 inputs_present=[Path(r['input_path']).exists() for r in selected],
 missing_inputs_not_excluded=True,raw_data_byte_hashes_computed=False,scientific_execution=False,
 gates=['Explicit produced/empty receipt required before extraction adoption','Coverage must pass before prepare_dataset; it currently skips missing feature CSVs'])
(ROOT/'sar-campaign-validation.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
