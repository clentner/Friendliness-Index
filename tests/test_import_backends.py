"""Compare complete native/paged imports, including crossing geometry and POIs."""
import hashlib,json,os,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
import numpy as np
import osmium
from pilot.source import TO_METERS
from pilot.regional_source import SpatialSource
from pilot.metric import score


class BackendTests(unittest.TestCase):
    def test_native_and_paged_imports_are_exactly_equivalent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture=root/'fixture.osm.pbf'
            header=osmium.io.Header();header.set('osmosis_replication_timestamp','2026-10-01T20:22:06Z')
            coords={1:(-73.04,41.),2:(-72.96,41.),3:(-73.,41.0002),4:(-73.,41.),
                    5:(-73.008,41.002),6:(-72.992,41.002),7:(-73.,41.002),
                    8:(-73.001,41.001),9:(-72.999,41.001),10:(-72.999,41.003),11:(-73.001,41.003),12:(-73.,41.004)}
            with osmium.SimpleWriter(str(fixture),header=header) as writer:
                for nid,xy in coords.items():
                    tags={'amenity':'cafe'} if nid==3 else {'barrier':'gate','access':'private'} if nid==7 else {}
                    writer.add_node(osmium.osm.mutable.Node(id=nid,location=xy,version=1,tags=tags))
                for wid,refs,tags in [(100,[1,2],{'highway':'footway'}),
                    (101,[5,7,6],{'highway':'footway'}),(102,[5,6],{'highway':'service','access':'private','foot':'yes'}),
                    (200,[8,9,10,11,8],{})]:
                    writer.add_way(osmium.osm.mutable.Way(id=wid,nodes=refs,tags=tags,version=1))
                writer.add_relation(osmium.osm.mutable.Relation(id=300,version=1,tags={'amenity':'cafe'},members=[('r',301,'')]))
                writer.add_relation(osmium.osm.mutable.Relation(id=301,version=1,members=[('w',200,''),('n',12,'')]))
            ring=[(-73.005,40.995),(-72.995,40.995),(-72.995,41.005),(-73.005,41.005),(-73.005,40.995)]
            boundary={'elements':[{'type':'relation','tags':{'ISO3166-2':'US-NY'},'members':[
                {'role':'outer','geometry':[{'lon':x,'lat':y} for x,y in ring]}]}]}
            (root/'boundary.json').write_text(json.dumps(boundary));records=[]
            digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
            for state in ['new-york','massachusetts','connecticut','vermont','new-jersey','pennsylvania','rhode-island','ontario','quebec']:
                name=state+'-261001.osm.pbf';os.link(fixture,root/name)
                (root/(state+'.poly')).write_text('fixture\n1\n -74 40\n -72 40\n -72 42\n -74 42\n -74 40\nEND\nEND\n')
                records.append({'path':name,'sha256':digest,'bytes':fixture.stat().st_size})
            (root/'sources.json').write_text(json.dumps(records))
            for backend in ['native','paged']:
                subprocess.run([sys.executable,'-c',
                    'import sys;from pilot.regional_source import index_sources;index_sources(sys.argv[1],sys.argv[2],coordinate_backend=sys.argv[3])',
                    str(root),str(root/(backend+'.sqlite')),backend],check=True,capture_output=True,text=True)
            with sqlite3.connect(root/'native.sqlite') as native,sqlite3.connect(root/'paged.sqlite') as paged:
                for table in ['vertices','raw_edges','pois','ways','relations','member_bounds','blocked','edges','spatial']:
                    first=native.execute('SELECT * FROM '+table).fetchall();second=paged.execute('SELECT * FROM '+table).fetchall()
                    self.assertEqual(sorted(first),sorted(second),table)
                self.assertEqual(paged.execute('SELECT count(*) FROM member_bounds WHERE k=?',('n12',)).fetchone()[0],1)
                self.assertGreater(paged.execute('SELECT count(*) FROM vertices').fetchone()[0],100)
            native.close();paged.close()
            x,y=TO_METERS.transform(-73.,41.);queries=np.array([[x,y],[x+100,y],[x+250,y+100]])
            a=SpatialSource(root/'native.sqlite');b=SpatialSource(root/'paged.sqlite')
            ga,pa=a.load((x-2000,y-2000,x+2000,y+2000));gb,pb=b.load((x-2000,y-2000,x+2000,y+2000))
            np.testing.assert_array_equal(score(ga,queries,pa)[0],score(gb,queries,pb)[0]);a.db.close();b.db.close()
