import hashlib,json,tempfile,unittest,subprocess,sys
from pathlib import Path
import numpy as np
import osmium
from pilot.locations import build_index,PagedLocations,PAGE_ROWS


class LocationTests(unittest.TestCase):
    def test_exact_native_equivalence_eviction_and_cache_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'fixture.osm.pbf';native=root/'native.locations'
            ids=[10000000000+i*7 for i in range(PAGE_ROWS*3+5)]
            with osmium.SimpleWriter(str(source)) as writer:
                for i,nid in enumerate(ids):
                    writer.add_node(osmium.osm.mutable.Node(id=nid,location=(-79.1234567+i/1e7,44.7654321-i/1e7),version=1))
            expected={}
            class Reference(osmium.SimpleHandler):
                def node(self,node):expected[node.id]=(node.location.lon,node.location.lat)
            Reference().apply_file(str(source))
            # libosmium's Windows cache handle can survive Python object
            # deletion. A short independent process provides a clean lifecycle.
            subprocess.run([sys.executable,'-c',
                "import osmium,sys;t=osmium.index.create_map('sparse_file_array,'+sys.argv[2]);h=osmium.NodeLocationsForWays(t);r=osmium.io.Reader(sys.argv[1],osmium.osm.NODE);osmium.apply(r,h);r.close()",
                str(source),str(native)],check=True)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            built=build_index(source,root/'coords',digest,reuse_native=native);meta=built.metadata;path=built.path;built.close()
            self.assertTrue(meta['native_cache_verified_every_node']);self.assertEqual(meta['rows'],len(ids))
            cache=PagedLocations(path,meta,max_pages=1)
            query=[ids[-1],ids[0],ids[PAGE_ROWS],ids[PAGE_ROWS*2],ids[7],ids[-1]]
            lon,lat=cache.lookup(query)
            np.testing.assert_array_equal(np.column_stack((lon,lat)),[expected[n] for n in query])
            self.assertLessEqual(cache.stats()['resident_cache_bytes'],PAGE_ROWS*16)
            with self.assertRaises(KeyError):cache.lookup([ids[0]+1])
            ticks,found=cache.ticks([ids[0]-1,ids[7],ids[-1]+1],allow_missing=True)
            np.testing.assert_array_equal(found,[False,True,False]);cache.close()
            reopened=build_index(source,root/'coords',digest);reopened.close()
            with self.assertRaises(ValueError):build_index(source,root/'coords','different')
            with path.open('r+b') as stream:stream.seek(8);stream.write(b'XXXXXXXX')
            with self.assertRaises(ValueError):build_index(source,root/'coords',digest)

    def test_fresh_index_matches_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'fresh.osm.pbf'
            coords=[(-179.9999999,-89.9999999),(0.,0.),(179.9999999,89.9999999)]
            with osmium.SimpleWriter(str(source)) as writer:
                for nid,xy in zip([1,300,20000000000],coords):writer.add_node(osmium.osm.mutable.Node(id=nid,location=xy,version=1))
            expected=[]
            class Reference(osmium.SimpleHandler):
                def node(self,node):expected.append((node.location.lon,node.location.lat))
            Reference().apply_file(str(source))
            digest=hashlib.sha256(source.read_bytes()).hexdigest();cache=build_index(source,root/'coords',digest)
            lon,lat=cache.lookup([1,300,20000000000]);np.testing.assert_array_equal(np.column_stack((lon,lat)),expected)
            cache.close()
