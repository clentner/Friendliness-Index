import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
import numpy as np
from pilot.raster import DiskRaster
from pilot.region import sparse_tiles,region_label
from pilot.regional_source import boundary
from pilot.source import TO_METERS


class ExpansionTests(unittest.TestCase):
    def test_sparse_candidate_envelopes_cover_ny_projected_cells(self):
        from pilot.region import block_tile_candidates
        from pilot.source import TO_WGS
        from pilot.tiles import tile_coordinate
        import math
        for lon,lat in [(-79.76,42.),(-78.87,42.88),(-74.,40.7),(-71.94,41.04),(-73.4,45.)]:
            x,y=TO_METERS.transform(lon,lat);origin=(math.floor(x/25)*25,math.floor(y/25)*25)
            candidates=block_tile_candidates(origin,0,0,(320,320))
            for row in [0,1,159,318,319]:
                for col in [0,1,159,318,319]:
                    a,b=TO_WGS.transform(origin[0]+(col+.5)*25,origin[1]+(row+.5)*25)
                    tx,ty=tile_coordinate(a,b,14)
                    self.assertIn((math.floor(tx),math.floor(ty)),candidates)

    def test_block_selector_matches_independent_native_reader(self):
        import osmium
        from scripts.pbf_node_scan import scan
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.osm.pbf'
            coords={1:(-73.7,41.1),30:(-73.5,41.1),10000:(-72.3,41.2),10001:(-73.2,41.6),10002:(-72.1,40.95)}
            with osmium.SimpleWriter(str(path)) as writer:
                for nid,xy in coords.items():writer.add_node(osmium.osm.mutable.Node(id=nid,location=xy,version=1))
            selected={}
            def accept(ids,x,y):selected.update({int(i):(float(a),float(b)) for i,a,b in zip(ids,x,y)})
            bbox=(-73.68,40.94,-71.99,41.32)
            result=scan(path,[bbox],accept)
            native={}
            class Reference(osmium.SimpleHandler):
                def node(self,n):
                    x,y=n.location.lon,n.location.lat
                    if bbox[0]<=x<=bbox[2] and bbox[1]<=y<=bbox[3]:native[n.id]=(x,y)
            Reference().apply_file(str(path))
            self.assertEqual(set(selected),set(native));self.assertEqual(result['nodes'],len(coords))
            for key in native:np.testing.assert_allclose(selected[key],native[key],atol=1e-12,rtol=0)

    def test_block_scan_resume_keeps_exact_node_selection(self):
        import osmium
        from scripts.pbf_node_scan import scan,full_blocks
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'resume.osm.pbf'
            with osmium.SimpleWriter(str(path)) as writer:
                for nid in range(1,16002):writer.add_node(osmium.osm.mutable.Node(id=nid,location=(-73.,41.),version=1))
            blocks=list(full_blocks(path,with_offsets=True))
            self.assertGreater(len(blocks),1)
            first=blocks[0][0]
            first_ids=[]
            for group in first.groups:
                first_ids.extend(int(n) for n in np.cumsum(np.fromiter(group.dense.id,dtype=np.int64)))
                first_ids.extend(n.id for n in group.nodes)
            selected=list(first_ids)
            result=scan(path,[(-74.,40.,-72.,42.)],lambda ids,x,y:selected.extend(int(n) for n in ids),
                resume={'nodes':len(first_ids),'blocks':1,'selected':len(first_ids),'bytes_read':blocks[1][1]})
            self.assertEqual(selected,list(range(1,16002)))
            self.assertEqual(result['nodes'],16001);self.assertEqual(result['selected'],16001)

    def test_parent_gap_extract_completes_way_and_nested_poi(self):
        import osmium
        from shapely.geometry import box,mapping
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'parent.osm.pbf';out=root/'context.osm.pbf';report=root/'report.json'
            x,y=TO_METERS.transform(-73.,41.)
            gaps=root/'gaps.json';gaps.write_text(json.dumps(mapping(box(x-10,y-10,x+10,y+10))))
            header=osmium.io.Header();header.set('osmosis_replication_timestamp','2026-10-01T20:22:06Z')
            with osmium.SimpleWriter(str(parent),header=header) as writer:
                for nid,xy in [(1,(-73.,41.)),(2,(-73.1,41.)),(3,(-74.,42.))]:
                    writer.add_node(osmium.osm.mutable.Node(id=nid,version=1,location=xy))
                writer.add_way(osmium.osm.mutable.Way(id=100,version=1,nodes=[1,2],tags={'highway':'footway'}))
                writer.add_relation(osmium.osm.mutable.Relation(id=10,version=1,tags={'amenity':'cafe'},members=[('r',20,'')]))
                writer.add_relation(osmium.osm.mutable.Relation(id=20,version=1,members=[('w',100,'')]))
            subprocess.run([sys.executable,'scripts/extract_ny_gap_parent.py','--parent',str(parent),'--out',str(out),
                '--report',str(report),'--gaps',str(gaps)],check=True,capture_output=True,text=True)
            result=json.loads(report.read_text())
            self.assertEqual((result['initial_nodes'],result['nodes'],result['ways'],result['relations']),(1,2,1,2))
            class Reference(osmium.SimpleHandler):
                def way(self,w):self.refs=[n.ref for n in w.nodes]
            reference=Reference();reference.apply_file(str(out))
            self.assertEqual(reference.refs,[1,2])

    def test_windowed_raster_preserves_nan_zero_and_arbitrary_indices(self):
        with tempfile.TemporaryDirectory() as tmp:
            raster=DiskRaster(Path(tmp)/'scores.f32',(153,40),create=True)
            expected=np.full((153,40),np.nan,dtype='<f4')
            values=np.arange(100,dtype='<f4').reshape(10,10)
            raster[60:70,2:12]=values;expected[60:70,2:12]=values
            rows=np.array([0,69,60,61,150]);cols=np.array([0,11,2,3,39])
            np.testing.assert_array_equal(raster[rows,cols],expected[rows,cols])
            np.testing.assert_array_equal(raster[50:75,0:20],expected[50:75,0:20])
            self.assertEqual((Path(tmp)/'scores.f32').stat().st_size,153*40*4)

    def test_export_resume_checks_payloads_and_preserves_empty_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);x,y=TO_METERS.transform(-71.,42.36)
            origin=np.floor(np.array([x,y])/25)*25-250
            scores=np.zeros((20,20),dtype='<f4');bbox=(-71.002,42.358,-70.998,42.362)
            first=sparse_tiles(root/'tiles',scores,origin,bbox,root/'progress')
            original={key:(root/'tiles'/(key+'.png')).read_bytes() for key in first}
            second=sparse_tiles(root/'tiles',scores,origin,bbox,root/'progress')
            self.assertEqual(first,second)
            self.assertTrue(all((root/'tiles'/(k+'.png')).read_bytes()==v for k,v in original.items()))
            (root/'tiles'/(first[0]+'.png')).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'checksum'):
                sparse_tiles(root/'tiles',scores,origin,bbox,root/'progress')

    def test_ny_boundary_retains_island_and_hole(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def ring(points,role):return {'role':role,'geometry':[{'lon':x,'lat':y} for x,y in points]}
            data={'elements':[{'tags':{'ISO3166-2':'US-NY'},'members':[
                ring([(-74,41),(-73,41),(-73,42),(-74,42),(-74,41)],'outer'),
                ring([(-73.9,41.1),(-73.8,41.1),(-73.8,41.2),(-73.9,41.2),(-73.9,41.1)],'inner'),
                ring([(-72.1,41),(-72,41),(-72,41.1),(-72.1,41.1),(-72.1,41)],'outer')]}]}
            (root/'boundary.json').write_text(json.dumps(data),encoding='utf-8')
            wgs,_=boundary(root/'boundary.json')
            self.assertEqual(len(wgs.geoms),2)
            self.assertAlmostEqual(wgs.area,1.)
            self.assertEqual(region_label(root),'New York State')


if __name__=='__main__':unittest.main()
