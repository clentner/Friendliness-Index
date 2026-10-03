"""Verify geometry, snapshot, source hashes and resource sizing before import."""
import hashlib
import json
from pathlib import Path
import shutil
import osmium
from shapely.geometry import Point, mapping
from shapely.ops import transform, unary_union
from pilot.regional_source import boundary,read_poly
from pilot.region import plan,NY_SAMPLE_LOCATIONS
from pilot.source import TO_METERS

root=Path('data/ny-20261001');records=json.loads((root/'sources.json').read_text())
wgs,core=boundary(root/'boundary.json');support=core.buffer(1025)
coverage=unary_union([transform(TO_METERS.transform,read_poly(root/r['poly'])) for r in records])
missing=support.difference(coverage)
stamps={};hashes={}
for r in records:
    with (root/r['path']).open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    assert sha==r['sha256'];hashes[r['path']]=sha
    with osmium.io.Reader(str(root/r['path'])) as reader:
        stamps[r['path']]=reader.header().get('osmosis_replication_timestamp')
locations={name:wgs.covers(Point(lon,lat)) for name,lon,lat in NY_SAMPLE_LOCATIONS}
report={'plan':plan(root),'snapshots':stamps,'verified_sha256':hashes,
    'pbf_bytes':sum(r['bytes'] for r in records),'missing_support_m2':missing.area,
    'representative_coverage':locations,'free_disk_bytes':shutil.disk_usage(root).free,
    'boundary_timestamp':json.loads((root/'boundary.json').read_text(encoding='utf-8')).get('osm3s',{}),
    'boundary_sha256':hashlib.sha256((root/'boundary.json').read_bytes()).hexdigest()}
Path('qa-artifacts/ny/source-check.json').write_text(json.dumps(report,indent=2))
if missing.area>1:
    Path('qa-artifacts/ny/missing-support.geojson').write_text(json.dumps(mapping(missing)))
print(json.dumps(report),flush=True)
assert len(set(stamps.values()))==1 and next(iter(stamps.values()))
assert missing.area<=1,'Source polygons do not cover full NY support'
assert all(locations.values()),'A representative NY location is outside the boundary'
