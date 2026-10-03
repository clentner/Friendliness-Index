"""Validate/reuse the completed Ontario node cache without touching graph DB."""
import hashlib,json
from pathlib import Path
from pilot.locations import build_index
from scripts.process_memory import snapshot

root=Path('data/ny-20261001')
record=next(r for r in json.loads((root/'sources.json').read_text()) if r['path']=='ontario-261001.osm.pbf')
source=root/record['path']
with source.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==record['sha256']
print(json.dumps({'phase':'before','memory':snapshot()}),flush=True)
cache=build_index(source,root/'node-locations',record['sha256'],
    reuse_native=root/'source.9e21e1d6f77646af928d33453afefe35.locations')
assert cache.rows==146892982 and cache.metadata['native_cache_verified_every_node']
report={k:v for k,v in cache.metadata.items() if k!='fences'}
report.update(cache=str(cache.path),memory=snapshot());cache.close()
Path('qa-artifacts/ny/ontario-coordinate-equivalence.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
