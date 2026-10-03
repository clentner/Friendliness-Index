"""Inventory the local NY build without modifying sources, checkpoints or output."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil


def inventory(root, identities):
    root=Path(root);counts=Counter();sizes=Counter();logical=0;unique=0;files=0
    if not root.exists():return {'exists':False,'path':str(root)}
    paths=[root] if root.is_file() else root.rglob('*')
    for path in paths:
        if not path.is_file():continue
        stat=path.stat();kind=path.suffix or '(no extension)'
        counts[kind]+=1;sizes[kind]+=stat.st_size;logical+=stat.st_size;files+=1
        identity=(stat.st_dev,stat.st_ino)
        if identity not in identities:
            identities.add(identity);unique+=stat.st_size
    return {'exists':True,'path':str(root),'files':files,'logical_bytes':logical,
            'unique_file_bytes_added':unique,
            'extensions':{kind:{'files':counts[kind],'bytes':sizes[kind]} for kind in sorted(counts)}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,default=Path('qa-artifacts/ny/build-resources.json'))
    args=parser.parse_args();root=Path('qa-artifacts/ny');groups={}
    for path in sorted(root.glob('*.resources.json')):
        name=path.name.removesuffix('.resources.json');base,_,attempt=name.rpartition('-')
        if not attempt.isdigit() or base not in {'ny-import','ny-samples','ny-access-audit','ny-seams',
                'ny-scoring','ny-scoring-summary','ny-export','ny-export-verification',
                'ny-display-overviews','ny-display-verification','ny-pixel-reference','ny-archives'}:continue
        data=json.loads(path.read_text());groups.setdefault(base,[]).append({'report':str(path),**data})
    stages={}
    for name,attempts in groups.items():
        attempts.sort(key=lambda a:int(Path(a['report']).name.removesuffix('.resources.json').rsplit('-',1)[1]))
        stages[name]={'attempts':attempts,'measured_attempt_seconds':sum(a['seconds'] for a in attempts),
            'peak_working_set_bytes':max(a['peak_working_set_bytes'] for a in attempts),
            'latest_finished': 'exit_code' in attempts[-1],
            'latest_success':attempts[-1].get('exit_code')==0 and attempts[-1].get('stopped_reason') is None}
    for name in ['stage-archives','stage-combined']:
        path=root/(name+'.resources.json')
        if path.exists():
            data=json.loads(path.read_text())
            stages[name]={'attempts':[{'report':str(path),**data}],
                'measured_attempt_seconds':data['seconds'],
                'peak_working_set_bytes':data['peak_working_set_bytes'],
                'latest_finished':'exit_code' in data,
                'latest_success':data.get('exit_code')==0 and data.get('stopped_reason') is None}
    identities=set();paths=['data/ny-20261001','data/ny-parent','build/ny-run','build/new-york',
                           'build/new-york-display','build/ny-archive-parts',
                           'build/archives/new-york-b42279c259905289-overview.pmtiles',
                           'build/archives/new-york-b42279c259905289-detail.pmtiles',
                           'build/new-york-pmtiles','build/ma-ny-pmtiles',
                           'qa-artifacts/ny/before-memory-fix','qa-artifacts/ny/before-relation-repair']
    inventories=[inventory(path,identities) for path in paths]
    report={'measured_at_utc':datetime.now(timezone.utc).isoformat(),'worker':json.loads((root/'worker-status.json').read_text()),
            'stages':stages,'inventories':inventories,
            'unique_file_bytes':sum(i.get('unique_file_bytes_added',0) for i in inventories),
            'disk_free_bytes':shutil.disk_usage('.').free,
            'notes':['Unique file bytes count each NTFS file identity once across listed directories; this is not allocated disk clusters.',
                     'Source hard links shared with MA count once here; they are not all incremental storage.',
                     'The combined site includes a preserved MA copy; local inventory is not incremental hosting. See combined-site.json for exact hosting changes.',
                     'Attempts include interruptions and checkpoint validation. Scoring/export times remain separate.',
                     'A missing exit_code means a live or interrupted measurement, not successful completion.',
                     'Inventories are observations of a running build, not an atomic snapshot or hosting quote.']}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:report[k] for k in ['measured_at_utc','worker','unique_file_bytes','disk_free_bytes']}))


if __name__=='__main__':main()
