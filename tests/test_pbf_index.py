import hashlib,json,tempfile,unittest
from pathlib import Path
import osmium
from scripts.pbf_block_index import build
from scripts.pbf_node_scan import full_blocks,selected_offsets,block_at


class BlockIndexTests(unittest.TestCase):
    def test_resume_and_selected_ids_match_full_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'fixture.osm.pbf';cache=root/'index.json'
            with osmium.SimpleWriter(str(source)) as writer:
                for nid in range(1,16002):writer.add_node(osmium.osm.mutable.Node(id=nid,version=1,location=(-73.,41.)))
                writer.add_way(osmium.osm.mutable.Way(id=1000000001,version=1,nodes=[1,16001]))
                writer.add_relation(osmium.osm.mutable.Relation(id=123456,version=1,members=[('w',1000000001,'')]))
            digest=hashlib.sha256(source.read_bytes()).hexdigest();full=build(source,cache,digest)
            self.assertEqual(build(source,cache,digest),full)
            first=next(full_blocks(source,with_end_offsets=True));offset=first[2]
            partial={**full,'offset':offset,'blocks':1,'index':{kind:[r for r in rows if r[2]<offset] for kind,rows in full['index'].items()}}
            partial['index_sha256']=hashlib.sha256(json.dumps(partial['index'],separators=(',',':')).encode()).hexdigest()
            resumed=root/'resume.json';resumed.with_suffix('.partial.json').write_text(json.dumps(partial))
            self.assertEqual(build(source,resumed,digest)['index'],full['index'])
            with source.open('rb') as stream:
                blocks=[block_at(stream,p) for p in selected_offsets(full['index']['w'],{1000000001})]
            self.assertIn(1000000001,[w.id for b in blocks for g in b.groups for w in g.ways])
            broken=json.loads(cache.read_text());broken['index']['n'][0][0]+=1;cache.write_text(json.dumps(broken))
            with self.assertRaisesRegex(ValueError,'checksum'):build(source,cache,digest)
            with self.assertRaisesRegex(ValueError,'Parent checksum'):build(source,cache,'wrong')


if __name__=='__main__':unittest.main()
