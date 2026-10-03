import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
import osmium
from shapely.geometry import box
from pilot.source import TO_METERS
from pilot.regional_source import SpatialSource,import_identity,validate_relation_completion
from scripts.pbf_block_index import build
from scripts.relation_context import extract,audit
from scripts.repair_ny_relations import protect_graph


class RelationContextTests(unittest.TestCase):
    def fixture(self,path):
        header=osmium.io.Header();header.set('osmosis_replication_timestamp','2026-10-01T20:22:06Z')
        with osmium.SimpleWriter(str(path),header=header) as writer:
            for nid,xy in [(1,(-76.6,39.6)),(2,(-76.61,39.61)),(3,(-76.62,39.62)),(4,(-74.,41.)),(5,(-74.001,41.001))]:
                writer.add_node(osmium.osm.mutable.Node(id=nid,version=1,location=xy))
            for wid,refs in [(1001,[1,2]),(1002,[2,3]),(2001,[4,5])]:writer.add_way(osmium.osm.mutable.Way(id=wid,version=1,nodes=refs))
            for rid,members in [(30000,[('w',1001,''),('r',30001,'')]),(30001,[('w',1002,'')]),(40000,[('w',1001,''),('w',2001,'')])]:
                writer.add_relation(osmium.osm.mutable.Relation(id=rid,version=2,members=members,tags={'leisure':'park'}))
        x,y=TO_METERS.transform(-74.,41.)
        return box(x-2000,y-2000,x+2000,y+2000),json.loads(Path('poi_config.json').read_text())

    def test_full_nested_geometry_and_partial_geometry_trap(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'parent.osm.pbf';support,config=self.fixture(source)
            index=build(source,root/'index.json',hashlib.sha256(source.read_bytes()).hexdigest())['index']
            out=root/'remote.osm.pbf';counts=extract(source,index,[30000],out)
            self.assertEqual(counts,{'n':3,'w':2,'r':2})
            expected={30000:(2,[('w',1001),('r',30001)]),30001:(2,[('w',1002)])}
            result,bounds=audit(out,[30000],expected,support,config,{'w1001':(-76.61,39.6,-76.6,39.61)})
            self.assertEqual(result['roots'][0]['bounds_wgs'],[-76.62,39.6,-76.6,39.62])
            self.assertGreater(result['roots'][0]['geometry_distance_to_support_m'],100000)
            with self.assertRaisesRegex(ValueError,'version'):audit(out,[30000],{30000:(3,[('w',1001),('r',30001)])},support,config)
            with self.assertRaisesRegex(ValueError,'retained member'):audit(out,[30000],expected,support,config,{'w1001':(0,0,1,1)})
            crossing=root/'crossing.osm.pbf';extract(source,index,[40000],crossing)
            with self.assertRaisesRegex(ValueError,'may affect NY'):
                audit(crossing,[40000],{40000:(2,[('w',1001),('w',2001)])},support,config)

    def test_missing_node_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'incomplete.osm.pbf'
            with osmium.SimpleWriter(str(path)) as writer:
                writer.add_node(osmium.osm.mutable.Node(id=1,location=(-76.,39.)))
                writer.add_way(osmium.osm.mutable.Way(id=2,nodes=[1,999]))
            with self.assertRaisesRegex(ValueError,'Incomplete'):audit(path,[],{},box(0,0,1,1),{})

    def test_graph_authorizer_and_unresolved_scoring_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.sqlite';db=sqlite3.connect(path)
            db.executescript('CREATE TABLE edges(u INTEGER);INSERT INTO edges VALUES(1);CREATE TABLE member_bounds(k TEXT);CREATE TABLE metadata(k TEXT,value TEXT);')
            db.set_authorizer(protect_graph)
            with self.assertRaises(sqlite3.DatabaseError):db.execute('DELETE FROM edges')
            db.execute('INSERT INTO member_bounds VALUES(?)',('w1',))
            db.execute('INSERT INTO metadata VALUES(?,?)',('complete',json.dumps({'unresolved_relation_ids':[1]})))
            db.commit();self.assertEqual(db.execute('SELECT * FROM edges').fetchall(),[(1,)]);db.close()
            with self.assertRaisesRegex(ValueError,'blocks scoring'):SpatialSource(path)

    def test_completion_proof_and_extract_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'sources.json').write_text('[]');(root/'boundary.json').write_text('{}')
            extract_path=root/'context.pbf';extract_path.write_bytes(b'fixture')
            report={'extract':extract_path.name,'extract_sha256':hashlib.sha256(b'fixture').hexdigest(),
                    'import_identity':import_identity(root),'timestamp':'dated','unresolved_before':[1],
                    'roots':[{'id':1,'complete_geometry_outside_support':True}]}
            proof=root/'proof.json';proof.write_text(json.dumps(report))
            metadata={'osm_timestamp':'dated','relation_completion':{'report':proof.name,'sha256':hashlib.sha256(proof.read_bytes()).hexdigest(),'resolved_relations':[1]}}
            validate_relation_completion(root,metadata)
            extract_path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'extract changed'):validate_relation_completion(root,metadata)
            proof.write_text('{}')
            with self.assertRaisesRegex(ValueError,'proof changed'):validate_relation_completion(root,metadata)


if __name__=='__main__':unittest.main()
