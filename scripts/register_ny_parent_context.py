"""Register only a fully verified and reference-complete dated gap artifact."""
import hashlib,json
from pathlib import Path
import osmium

root=Path('data/ny-20261001');report_path=root/'sound-context.derivation.json'
report=json.loads(report_path.read_text());parent=json.loads(Path('data/ny-parent/parent.json').read_text())
assert report['parent']['parent_sha256']==parent['sha256']
path=Path(report['path']);poly=Path(report['poly'])
assert path.parent.resolve()==root.resolve() and poly.parent.resolve()==root.resolve()
assert hashlib.sha256(path.read_bytes()).hexdigest()==report['sha256']
assert hashlib.sha256(poly.read_bytes()).hexdigest()==report['poly_sha256']
nodes=set();ways=set();relations={};way_refs=set()
class Check(osmium.SimpleHandler):
    def node(self,n):nodes.add(n.id)
    def way(self,w):ways.add(w.id);way_refs.update(n.ref for n in w.nodes)
    def relation(self,r):relations[r.id]=[(m.type,m.ref) for m in r.members]
Check().apply_file(str(path))
assert (len(nodes),len(ways),len(relations))==(report['nodes'],report['ways'],report['relations']),'Independent reader counts differ from extraction plan'
assert way_refs<=nodes,'Incomplete supplemental way'
for rid,members in relations.items():
    for kind,ref in members:assert ref in {'n':nodes,'w':ways,'r':relations}[kind],(rid,kind,ref)
records=[r for r in json.loads((root/'sources.json').read_text()) if not r.get('supplemental')]
record={'path':path.name,'poly':poly.name,'url':parent['url'],'bytes':path.stat().st_size,
    'sha256':report['sha256'],'poly_sha256':report['poly_sha256'],'supplemental':True,
    'kind':'dated-parent-context','derivation':report_path.name,
    'derivation_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
    'parent_sha256':parent['sha256'],'parent_bytes':parent['bytes'],
    'reference_complete':{'nodes':len(nodes),'ways':len(ways),'relations':len(relations)}}
records.append(record);temporary=root/'sources.complete.json';temporary.write_text(json.dumps(records,indent=2));temporary.replace(root/'sources.json')
print(json.dumps(record))
