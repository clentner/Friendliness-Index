import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from shapely.geometry import box
from pilot import metric
from pilot.region import Grid,sparse_tiles
from pilot.regional_source import connect,segment_records,SpatialSource,index_sources


class RegionTests(unittest.TestCase):
    def test_sparse_tiles_keep_zero_and_statewide_overviews(self):
        from PIL import Image
        from pilot.source import TO_METERS
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);x,y=TO_METERS.transform(-71.,42.36)
            origin=np.floor(np.array([x,y])/25)*25-250
            scores=np.zeros((20,20),dtype='<f4')
            bbox=(-71.002,42.358,-70.998,42.362)
            available=sparse_tiles(root/'visible',scores,origin,bbox)
            self.assertEqual({int(k.split('/')[0]) for k in available},set(range(7,15)))
            for key in available:
                with Image.open(root/'visible'/(key+'.png')) as image:
                    self.assertGreater(image.getchannel('A').getextrema()[1],0)
            scores[:]=np.nan
            self.assertEqual(sparse_tiles(root/'empty',scores,origin,bbox),[])

    def test_chunk_ownership_is_exact_on_absolute_lattice(self):
        core=box(-2101,-21,2028,2001);grid=Grid.covering(core.bounds)
        ownership=np.zeros(grid.shape,dtype=np.uint8)
        for job in grid.jobs(core):
            cx,cy,r0,r1,c0,c1=job
            q=grid.queries(job)
            self.assertLessEqual(len(q),6400)
            self.assertTrue(np.all(np.floor(q/2000)==[cx,cy]))
            ownership[r0:r1,c0:c1]+=1
        self.assertTrue(np.all(ownership==1))

    def test_subdivision_keeps_crossing_segments_and_osm_identity(self):
        # Neither original endpoint is inside the eventual scoring halo.
        vertices,edges=segment_records(11,12,(-2000,0),(2000,0),100,0)
        reverse,back=segment_records(12,11,(2000,0),(-2000,0),101,0)
        self.assertEqual({v[0] for v in vertices},{v[0] for v in reverse})
        self.assertEqual({(a,b) for a,b,_ in edges},{(a,b) for a,b,_ in back})
        self.assertTrue(any(v[1:3]==(0.0,0.0) for v in vertices))
        other,_=segment_records(21,22,(-2000,0),(2000,0),102,0)
        self.assertFalse({v[0] for v in vertices}&{v[0] for v in other})

    def test_disk_halos_match_global_scores_with_ties_and_duplicate_pois(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.sqlite';db=connect(path)
            db.executescript('''CREATE TABLE vertices(id INTEGER PRIMARY KEY,k TEXT UNIQUE,x REAL,y REAL,rank TEXT);
              CREATE TABLE edges(u INTEGER,v INTEGER,length REAL);CREATE INDEX edges_u ON edges(u);
              CREATE VIRTUAL TABLE spatial USING rtree(id,x0,x1,y0,y1);
              CREATE TABLE pois(k TEXT PRIMARY KEY,x REAL,y REAL);CREATE TABLE metadata(k TEXT,value TEXT);''')
            # Coincident disconnected roads: lower globally stable rank wins,
            # even if database insertion order and local spatial order differ.
            a,ae=segment_records(1,2,(-2000,0),(5000,0),10,0)
            b,be=segment_records(3,4,(-2000,0),(5000,0),20,0)
            for v in b+a:db.execute('INSERT INTO vertices(k,x,y,rank) VALUES(?,?,?,?)',v)
            ids=dict(db.execute('SELECT k,id FROM vertices'))
            db.executemany('INSERT INTO edges VALUES(?,?,?)',[(ids[u],ids[v],d) for u,v,d in ae+be])
            db.execute('INSERT INTO spatial SELECT id,x,x,y,y FROM vertices')
            pois=[(-500,10),(1995,5),(1995,5),(2800,10)]
            db.executemany('INSERT INTO pois VALUES(?,?,?)',[(str(i),*p) for i,p in enumerate(pois)])
            db.execute('INSERT INTO metadata VALUES(?,?)',('complete',json.dumps({})));db.commit();db.close()
            source=SpatialSource(path)
            global_graph,global_pois=source.load((-3000,-100,6000,100))
            queries=np.array([[x,0] for x in [0,25,1975,2000,2025,3975,4000]])
            expected,_=metric.score(global_graph,queries,global_pois)
            actual=np.empty(len(queries))
            for cx in range(3):
                selected=np.floor(queries[:,0]/2000)==cx
                local,p=source.load((cx*2000-metric.HALO,-metric.HALO,(cx+1)*2000+metric.HALO,2000+metric.HALO))
                actual[selected],_=metric.score(local,queries[selected],p)
            np.testing.assert_allclose(actual,expected,rtol=1e-12,atol=1e-12)
            source.db.close()

    def test_grid_uses_same_centers_as_pilot(self):
        grid=Grid.covering([322001,4688001,324123,4690011])
        self.assertEqual(grid.origin,(322000.,4688000.))
        self.assertEqual(grid.shape,(81,85))

    def test_streamed_pbf_matches_existing_importer(self):
        import osmium
        from pilot.source import load,acquisition_filter_hash,TO_METERS
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=json.loads(Path('poi_config.json').read_text())
            ring=[(-71.01,42.35),(-70.99,42.35),(-70.99,42.37),(-71.01,42.37),(-71.01,42.35)]
            boundary_data={'elements':[{'tags':{'ISO3166-2':'US-MA'},'members':[{'role':'outer','geometry':[{'lon':x,'lat':y} for x,y in ring]}]}]}
            (root/'boundary.json').write_text(json.dumps(boundary_data))
            nodes={1:(-71.01,42.36),2:(-71.,42.36),3:(-70.99,42.36),
                   10:(-71.001,42.3601),11:(-71.,42.3601),12:(-71.,42.3602),13:(-71.001,42.3602)}
            ways=[(1,[1,2,3],{'highway':'footway'}),(2,[3,2,1],{'highway':'footway'}),
                  (10,[10,11,12,13,10],{'amenity':'cafe'})]
            elements=[]
            for nid,(lon,lat) in nodes.items():
                elements.append({'type':'node','id':nid,'lon':lon,'lat':lat,'tags':{'amenity':'cafe'} if nid==2 else {}})
            for wid,refs,tags in ways:
                elements.append({'type':'way','id':wid,'nodes':refs,'tags':tags,'geometry':[{'lon':nodes[n][0],'lat':nodes[n][1]} for n in refs]})
            elements.append({'type':'relation','id':50,'tags':{'amenity':'cafe'},'center':{'lon':-71.0005,'lat':42.36015}})
            records=[]
            for state in ['massachusetts','connecticut','rhode-island','new-hampshire','vermont','new-york']:
                name=state+'-261001.osm.pbf';path=root/name;header=osmium.io.Header();header.set('osmosis_replication_timestamp','2026-10-01T00:00:00Z')
                with osmium.SimpleWriter(str(path),header=header) as writer:
                    for nid,(lon,lat) in nodes.items():writer.add_node(osmium.osm.mutable.Node(id=nid,version=1,location=(lon,lat),tags={'amenity':'cafe'} if nid==2 else {}))
                    for wid,refs,tags in ways:writer.add_way(osmium.osm.mutable.Way(id=wid,version=1,nodes=refs,tags=tags))
                    writer.add_relation(osmium.osm.mutable.Relation(id=50,version=1,tags={'amenity':'cafe'},members=[('r',51,'outer')]))
                    writer.add_relation(osmium.osm.mutable.Relation(id=51,version=1,tags={'type':'multipolygon'},members=[('w',10,'outer')]))
                (root/(state+'.poly')).write_text('test\n1\n -72 41\n -70 41\n -70 43\n -72 43\n -72 41\nEND\nEND\n')
                records.append({'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            (root/'sources.json').write_text(json.dumps(records))
            # Pyosmium's Windows mapping handle is released at process exit.
            # Isolate the native importer so the fixture can be removed cleanly.
            subprocess.run([sys.executable,'-c',
                'from pilot.regional_source import index_sources;import sys;index_sources(sys.argv[1],sys.argv[2])',
                str(root),str(root/'source.sqlite')],check=True,capture_output=True,text=True)
            metadata=json.loads((root/'source.json').read_text())
            self.assertEqual(metadata['pois'],3)
            self.assertEqual(metadata['unresolved_relation_ids'],[])
            # Simulate interruption after a committed batch but before the
            # final source checkpoint; replay must preserve graph/POI identity.
            db=connect(root/'source.sqlite')
            db.execute("DELETE FROM metadata WHERE k IN ('complete','file:new-york-261001.osm.pbf')")
            db.execute('DELETE FROM ways WHERE id=1');db.commit();db.close()
            subprocess.run([sys.executable,'-c',
                'from pilot.regional_source import index_sources;import sys;index_sources(sys.argv[1],sys.argv[2],resume=True)',
                str(root),str(root/'source.sqlite')],check=True,capture_output=True,text=True)
            resumed=json.loads((root/'source.json').read_text())
            for key in ['nodes','edges','pois','unresolved_relation_ids']:
                self.assertEqual(metadata[key],resumed[key])
            original=(root/'sources.json').read_text()
            (root/'sources.json').write_text(original+' ')
            with self.assertRaisesRegex(ValueError,'provenance'):
                index_sources(root,root/'source.sqlite',resume=True)
            (root/'sources.json').write_text(original)
            raw=json.dumps({'elements':elements}).encode();(root/'source.json').write_bytes(raw)
            (root/'source.json.meta.json').write_text(json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'coverage_bbox':[-72,41,-70,43],
                'acquisition_poi_allow_sha256':acquisition_filter_hash(config)}))
            reference,pois,_=load(root/'source.json',[-71.005,42.355,-70.995,42.365])
            source=SpatialSource(root/'source.sqlite');graph,local_pois=source.load((0,4000000,800000,5000000))
            queries=np.array([TO_METERS.transform(x,42.36) for x in [-71.006,-71.,-70.996]])
            expected,_=metric.score(reference,queries,pois);actual,_=metric.score(graph,queries,local_pois)
            np.testing.assert_allclose(actual,expected,rtol=1e-9,atol=1e-10)
            source.db.close()

if __name__=='__main__':unittest.main()
