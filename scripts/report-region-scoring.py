"""Summarize completed regional checkpoints without changing build inputs."""
import json
from pathlib import Path
import numpy as np
import argparse

parser=argparse.ArgumentParser()
parser.add_argument('--run',type=Path,default=Path('build/ma-run'))
parser.add_argument('--report',type=Path,default=Path('qa-artifacts/scoring-summary.json'))
args=parser.parse_args();run=args.run
jobs=[json.loads(p.read_text()) for p in (run/'chunks').glob('*.json')]
assert len(jobs)==json.loads((run/'run.json').read_text())['plan']['scoring_jobs']
durations=[j['seconds'] for j in jobs]
result={'jobs':len(jobs),'inside_cells':sum(j['inside_cells'] for j in jobs),
        'reachable_cells':sum(j['reachable'] for j in jobs),'empty_jobs':sum(j['reachable']==0 for j in jobs),
        'summed_job_seconds':sum(durations),'median_job_seconds':float(np.median(durations)),
        'p95_job_seconds':float(np.percentile(durations,95)),'max_job_seconds':max(durations),
        'max_halo_vertices':max(j['nodes'] for j in jobs),'max_halo_pois':max(j['pois'] for j in jobs),
        'total_reverse_searches':sum(j['searches'] for j in jobs),
        'representatives':[j for j in jobs if 'location' in j]}
result['total_load_seconds']=sum(j.get('load_seconds',0) for j in jobs)
result['total_score_seconds']=sum(j.get('score_seconds',0) for j in jobs)
result['timing_notes']=[
    'load_seconds measures source graph/POI loading.',
    'score_seconds includes metric scoring and NPY checkpoint writing, hashing and rename; it is not an isolated kernel CPU timer.',
    'Summed job seconds include reused representative jobs; monitored statewide wall time excludes their recomputation.']
result['slowest_jobs']=sorted(jobs,key=lambda j:-j['seconds'])[:20]
args.report.write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='representatives'}))
