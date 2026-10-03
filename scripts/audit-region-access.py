"""Audit legacy Overpass acquisition/access interactions on the actual PBFs."""
import json
import os
from pathlib import Path
import sqlite3
import time
import argparse
for name in ['OSMIUM_POOL_THREADS','OSMIUM_MAX_INPUT_QUEUE_SIZE','OSMIUM_MAX_OSMDATA_QUEUE_SIZE','OSMIUM_MAX_WORK_QUEUE_SIZE']:
    os.environ.setdefault(name,'2')
import osmium
from pilot.source import allowed_poi,permitted

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=Path('data/ma-20261001'))
parser.add_argument('--run',type=Path,default=Path('build/ma-run'))
parser.add_argument('--report',type=Path,default=Path('qa-artifacts/region-access-audit.json'))
args=parser.parse_args()
started=time.monotonic();root=args.root;config=json.loads(Path('poi_config.json').read_text())
db=sqlite3.connect(root/'source.sqlite');candidates=set();affected=set()
class Audit(osmium.SimpleHandler):
    def node(self,n):
        tags=dict(n.tags)
        selected=any(tag in tags and ('*' in values or tags[tag] in values) for tag,values in config['allow'].items())
        if selected and not allowed_poi(tags,config) and not permitted(tags) and 'barrier' not in tags:
            candidates.add(n.id)
            if db.execute('SELECT 1 FROM vertices WHERE k=?',(f'n{n.id}',)).fetchone():affected.add(n.id)
handler=Audit()
for record in json.loads((root/'sources.json').read_text()):
    with osmium.io.Reader(str(root/record['path']),osmium.osm.NODE) as reader:
        osmium.apply(reader,osmium.filter.KeyFilter(*config['allow']),handler)
    print(json.dumps({'audited':record['path'],'candidates':len(candidates),'retained_graph_matches':len(affected)}),flush=True)
report={'candidate_private_nodes_filtered_by_poi_deny':len(candidates),'retained_graph_node_ids':sorted(affected),
        'run_signature':json.loads((args.run/'run.json').read_text())['signature'],
        'seconds':time.monotonic()-started}
args.report.write_text(json.dumps(report,indent=2))
print(json.dumps(report));assert not affected,'Legacy acquisition/access edge case affects retained graph; source repair required'
