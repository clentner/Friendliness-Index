"""Read-only coordinate equivalence and resident-memory benchmark on real ways."""
import os
for key in ['OSMIUM_POOL_THREADS','OSMIUM_MAX_INPUT_QUEUE_SIZE','OSMIUM_MAX_OSMDATA_QUEUE_SIZE','OSMIUM_MAX_WORK_QUEUE_SIZE']:os.environ.setdefault(key,'2')
import argparse,gc,hashlib,json,struct,time
from pathlib import Path
import numpy as np
import osmium
from pilot.locations import DTYPE,PagedLocations
from scripts.process_memory import snapshot

parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['mapped','paged'],required=True)
parser.add_argument('--pbf',type=Path,required=True);parser.add_argument('--cache',type=Path,required=True)
parser.add_argument('--rows',type=int);parser.add_argument('--metadata',type=Path)
parser.add_argument('--limit',type=int,default=1000000);args=parser.parse_args()
started=time.monotonic();digest=hashlib.sha256()
if args.mode=='mapped':locations=np.memmap(args.cache,dtype=DTYPE,mode='r',shape=(args.rows,))
else:locations=PagedLocations(args.cache,json.loads(args.metadata.read_text()))
print(json.dumps({'phase':'before','memory':snapshot()}),flush=True)
class Finished(Exception):pass
class Ways(osmium.SimpleHandler):
    count=0;references=0
    def way(self,way):
        refs=np.fromiter((n.ref for n in way.nodes),dtype=np.int64)
        if args.mode=='mapped':
            positions=np.searchsorted(locations['id'],refs)
            assert (positions<len(locations)).all() and np.array_equal(locations['id'][positions],refs)
            ticks=np.column_stack((locations['x'][positions],locations['y'][positions]))
        else:ticks,_=locations.ticks(refs)
        digest.update(struct.pack('<q',way.id));digest.update(ticks.astype('<i4').tobytes())
        self.count+=1;self.references+=len(refs)
        if self.count%100000==0 or self.count==args.limit:
            print(json.dumps({'ways':self.count,'references':self.references,'sha256':digest.hexdigest(),
                'seconds':time.monotonic()-started,'memory':snapshot(),
                'cache':locations.stats() if args.mode=='paged' else None}),flush=True)
        if self.count>=args.limit:raise Finished()
handler=Ways()
try:
    with osmium.io.Reader(str(args.pbf),osmium.osm.WAY) as reader:osmium.apply(reader,handler)
except Finished:pass
del reader
if args.mode=='mapped':locations._mmap.close()
else:locations.close()
del locations;gc.collect()
print(json.dumps({'phase':'closed','ways':handler.count,'sha256':digest.hexdigest(),
    'seconds':time.monotonic()-started,'memory':snapshot()}),flush=True)
