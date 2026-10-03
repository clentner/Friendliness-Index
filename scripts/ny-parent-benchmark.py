"""Measure a bounded native PBF node scan before considering a US parent file."""
import os
for key in ['OSMIUM_POOL_THREADS','OSMIUM_MAX_INPUT_QUEUE_SIZE','OSMIUM_MAX_OSMDATA_QUEUE_SIZE','OSMIUM_MAX_WORK_QUEUE_SIZE']:os.environ.setdefault(key,'2')
import json,time
from pathlib import Path
import osmium

class Scan(osmium.SimpleHandler):
    count=0
    selected=0
    def node(self,n):
        self.count+=1
        lon=n.location.lon
        if -73.68<=lon<=-71.99 and 40.94<=n.location.lat<=41.32:self.selected+=1

start=time.monotonic();handler=Scan()
with osmium.io.Reader('data/ny-20261001/new-york-261001.osm.pbf',osmium.osm.NODE) as reader:osmium.apply(reader,handler)
report={'nodes':handler.count,'bbox_nodes':handler.selected,'seconds':time.monotonic()-start,
    'input_bytes':Path('data/ny-20261001/new-york-261001.osm.pbf').stat().st_size}
Path('qa-artifacts/ny/parent-node-benchmark.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
