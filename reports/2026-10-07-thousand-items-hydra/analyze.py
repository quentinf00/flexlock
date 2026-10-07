import csv, hashlib, json, statistics, subprocess
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
repo=Path('/ontap/user/qfebvre/flexlock-execution-validation')
base=Path('/ontap/user/qfebvre/flexlock-hydra-benchmark')
report=repo/'reports/2026-10-07-thousand-items-hydra'
report.mkdir(parents=True,exist_ok=False)
manifests=[base/'nfs-primary/manifest.json',base/'supplement/manifest.json']
all_runs=[]
for p in manifests:
 m=json.loads(p.read_text())
 if p.parent.name=='nfs-primary':assert len(m['runs'])==42 and all(r['exit_code']==0 for r in m['runs']),p
 assert all(r['measurement']['source_revision']==m['source_revision'] for r in m['runs'] if 'measurement' in r),p
 all_runs.extend(m['runs'])
 clean={k:v for k,v in m.items() if k!='runs'}
 clean['raw_manifest']=str(p)
 clean['raw_manifest_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 clean['runs']=[{k:v for k,v in r.items() if k not in ('stdout','stderr')} for r in m['runs']]
 (report/(p.parent.name+'-measurements.json')).write_text(json.dumps(clean,indent=2)+'\n')
groups=defaultdict(list)
for r in all_runs:
 if r['exit_code']==0:groups[(r['variant'],r['count'])].append(r['measurement'])
stats=[]
for (variant,n),ms in groups.items():
 for metric in ['seconds','artifact_files','artifact_bytes','peak_rss_kib']+['phase:'+p for p in ms[0]['phases']]:
  vals=[m['phases'][metric[6:]] if metric.startswith('phase:') else m[metric] for m in ms]
  stats.append(dict(variant=variant,count=n,metric=metric,repeats=len(vals),median=statistics.median(vals),minimum=min(vals),maximum=max(vals)))
with (report/'summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(stats[0]),lineterminator='\n');w.writeheader();w.writerows(stats)
(report/'summary.json').write_text(json.dumps(stats,indent=2)+'\n')
validation=[]
for r in all_runs:
 if r['exit_code']!=0:continue
 m=r['measurement'];out=Path(m['output'])
 if m['kind'].endswith('local'):
  products=list((out/'runs').rglob('product.json'))
  seen=set()
  for p in products:
   v=json.loads(p.read_text());i=v['item'];assert i not in seen,(out,i);seen.add(i)
   inputs=Path(next(c for c in [r['command'][r['command'].index('--inputs')+1]]))
   assert v['sha256']==hashlib.sha256((inputs/f'{i}.bin').read_bytes()).hexdigest(),p
  assert seen==set(range(m['count'])),out
  validation.append(dict(output=str(out),products=len(products),exact_membership=True,sha256_matches_inputs=True))
 if m['kind'].endswith('slurm'):
  assert m['details']['scheduler_calls']==1,out
  scripts=list(out.rglob('*.slurm')) if m['kind'].startswith('flexlock') else list(out.rglob('*submission.sh'))
  assert len(scripts)==1,(out,scripts)
  text=scripts[0].read_text()
  expected='--array=0-3' if m['kind'].startswith('flexlock') else f'--array=0-{m["count"]-1}%4'
  assert expected in text,(scripts[0],expected)
  assert not list((out/'runs').rglob('product.json')),out
  payloads=list(out.rglob('*.pkl'))
  assert len(payloads)==(1 if m['kind'].startswith('flexlock') else m['count']),(out,len(payloads))
  validation.append(dict(output=str(out),scheduler_calls=1,array_directive=expected,pickles=len(payloads),worker_products=0))
(report/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
def stat(v,metric='seconds'):
 return next(s for s in stats if s['variant']==v and s['count']==1000 and s['metric']==metric)
plt.rcParams.update({'font.size':11,'figure.dpi':150})
fig,axs=plt.subplots(1,2,figsize=(9,4))
for ax,variants,title in zip(axs,[['flexlock-slurm','hydra-slurm'],['flexlock-local','hydra-local']],['Submission preparation (mock sbatch)','Serial execution (actual products)']):
 s=[stat(v) for v in variants];vals=[x['median'] for x in s]
 ax.bar(['FlexLock','Hydra'],vals,color=['#3976af','#ce7435'],yerr=[[x['median']-x['minimum'] for x in s],[x['maximum']-x['median'] for x in s]],capsize=5)
 for i,v in enumerate(vals):ax.text(i,s[i]['maximum']+4,f'{v:.1f} s',ha='center')
 ax.set_title(title,fontsize=11);ax.set_ylabel('Seconds');ax.set_ylim(0,max(x['maximum'] for x in s)*1.18)
fig.suptitle('1,000 tiny items on NFS · median and range of 3 runs\nFlexLock source/data discovery disabled; provenance features differ',fontsize=12)
fig.tight_layout()
for ext in ['svg','png']:fig.savefig(report/f'primary-comparison.{ext}')
plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(10,4))
variants=['flexlock-local','batch16-local','tracked-local']
vals=[stat(v)['median'] for v in variants]
axs[0].bar(['Baseline\n3-run median','Batch 16\n1 sample','Source + data\n1 sample'],vals,color=['#3976af','#629f78','#8a67a1'])
for i,v in enumerate(vals):axs[0].text(i,v+3,f'{v:.1f} s',ha='center')
axs[0].set_ylabel('Seconds');axs[0].set_title('FlexLock complete serial execution');axs[0].set_ylim(0,max(vals)*1.18)
variants=['queue-1','queue-16','tmp-queue1','tmp-queue16'];vals=[stat(v)['median'] for v in variants]
axs[1].bar(['NFS\nbatch 1','NFS\nbatch 16','ext4\nbatch 1','ext4\nbatch 16'],vals,color=['#3976af','#629f78','#3976af','#629f78'])
for i,v in enumerate(vals):axs[1].text(i,v+.4,f'{v:.2f}',ha='center')
axs[1].set_ylabel('Seconds');axs[1].set_title('Queue insert + claim/finish; no task execution');axs[1].set_ylim(0,max(vals)*1.18)
fig.suptitle('Provenance and batching costs · 1,000 items',fontsize=12);fig.tight_layout()
for ext in ['svg','png']:fig.savefig(report/f'cost-components.{ext}')
plt.close(fig)
for p in report.glob('*.svg'):p.write_text('\n'.join(line.rstrip() for line in p.read_text().splitlines())+'\n')
print(json.dumps(dict(runs=len(all_runs),failures=sum(r['exit_code']!=0 for r in all_runs),validated=sum(v.get('products',0) for v in validation),report=str(report),key_stats=[stat(v) for v in ['flexlock-local','hydra-local','flexlock-slurm','hydra-slurm','tracked-local','batch16-local']] ),indent=2))
