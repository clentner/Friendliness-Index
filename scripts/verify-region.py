"""Verify a completed regional export against its exact analytical raster."""
import hashlib
import gzip
import json
from collections import defaultdict
from pathlib import Path
import sqlite3
import time
import argparse
import numpy as np
from PIL import Image
from pilot.raster import DiskRaster
from pilot.source import TO_WGS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--site',type=Path,default=Path('build/massachusetts'))
    parser.add_argument('--run',type=Path,default=Path('build/ma-run'))
    parser.add_argument('--source',type=Path,default=Path('data/ma-20261001/source.sqlite'))
    parser.add_argument('--audit',type=Path,default=Path('qa-artifacts/region-access-audit.json'))
    parser.add_argument('--report',type=Path,default=Path('qa-artifacts/region-verification.json'))
    parser.add_argument('--archive-staging',action='store_true')
    args=parser.parse_args()
    started=time.monotonic();site=args.site;run=args.run
    manifest=json.loads((site/'manifest.json').read_text())
    access=json.loads(args.audit.read_text())
    assert access['run_signature']==json.loads((run/'run.json').read_text())['signature']
    assert not access['retained_graph_node_ids'],'Legacy acquisition/access mismatch requires source repair'
    data=site/'datasets'/manifest['dataset']
    scores=DiskRaster(run/'scores.f32',tuple(manifest['grid']['shape']))
    with (run/'scores.f32').open('rb') as stream:
        assert hashlib.file_digest(stream,'sha256').hexdigest()==manifest['scores_sha256']
    parts=json.loads((data/'raw-index.json').read_text())['parts'];reachable=0;raw_gzip_bytes=0
    required_finest_tiles=set();zero_cells=0
    origin=manifest['grid']['origin_corner_m'];spacing=manifest['parameters']['grid_spacing_m']
    finest=manifest['maxzoom'];side=2**finest;coverage_check_seconds=0
    seen=set()
    for part in parts:
        row,col=part['row'],part['col'];h,w=part['shape']
        assert (row,col) not in seen;seen.add((row,col))
        raw=(data/part['path']).read_bytes()
        raw_gzip_bytes+=len(gzip.compress(raw,compresslevel=6,mtime=0))
        assert hashlib.sha256(raw).hexdigest()==part['sha256']
        values=np.frombuffer(raw,dtype='<f4').reshape(h,w)
        np.testing.assert_array_equal(values,scores[row:row+h,col:col+w])
        assert not np.isinf(values).any() and np.all(values[np.isfinite(values)]>=0)
        reachable+=int(np.isfinite(values).sum())
        zero_cells+=int(np.count_nonzero(values==0))
        # Independently transform every finite cell center; do not reuse the
        # exporter's block candidate envelopes. At NY/MA z14 resolution a 25 m
        # finite cell contains pixel centers in its center's tile, so that tile
        # cannot legitimately be omitted as transparent.
        coverage_started=time.monotonic()
        rr,cc=np.nonzero(np.isfinite(values))
        lon,lat=TO_WGS.transform(origin[0]+(col+cc+.5)*spacing,
                                origin[1]+(row+rr+.5)*spacing)
        tx=np.floor((lon+180)/360*side).astype(np.int64)
        ty=np.floor((1-np.arcsinh(np.tan(np.radians(lat)))/np.pi)/2*side).astype(np.int64)
        required_finest_tiles.update(int(key) for key in np.unique(tx*side+ty))
        coverage_check_seconds+=time.monotonic()-coverage_started
    # Missing raw blocks must represent only NaN, including all marine areas.
    for row in range(0,scores.shape[0],320):
        for col in range(0,scores.shape[1],320):
            if (row,col) not in seen:assert np.isnan(scores[row:row+320,col:col+320]).all()
    assert reachable==manifest['stats']['reachable']
    actual={p.relative_to(data/'tiles').as_posix()[:-4] for p in (data/'tiles').rglob('*.png')}
    assert actual==set(manifest['available_tiles']) and len(actual)==manifest['tiles']
    required_keys={f'{finest}/{key//side}/{key%side}' for key in required_finest_tiles}
    missing_finite_tiles=required_keys-actual
    assert not missing_finite_tiles, f'Finite analytical cells have missing tiles: {sorted(missing_finite_tiles)[:20]}'
    zoom_sizes=defaultdict(list);unique_png={};finest_pixels=0
    for key in actual:
        path=data/'tiles'/(key+'.png');raw=path.read_bytes();z=int(key.split('/')[0])
        zoom_sizes[z].append(len(raw));unique_png[hashlib.sha256(raw).hexdigest()]=len(raw)
        with Image.open(path) as im:
            assert im.size==(256,256) and im.mode=='RGBA'
            assert im.getchannel('A').getextrema()[1]>0
            if z==14:finest_pixels+=int(np.count_nonzero(np.asarray(im.getchannel('A'))))
    with Image.open(site/'transparent.png') as im:assert im.getchannel('A').getextrema()==(0,0)
    assets=[p for p in site.rglob('*') if p.is_file()]
    if not args.archive_staging:assert len(assets)<=20000
    assert max(p.stat().st_size for p in assets)<=25*1024**2
    by_zoom={z:{'files':len(sizes),'bytes':sum(sizes),'min_bytes':min(sizes),'max_bytes':max(sizes),
                'median_bytes':float(np.median(sizes)),'p95_bytes':float(np.percentile(sizes,95)),
                'png_to_rgba_ratio':sum(sizes)/(len(sizes)*256*256*4)} for z,sizes in sorted(zoom_sizes.items())}
    raw_bytes=sum((data/part['path']).stat().st_size for part in parts)
    plan=json.loads((run/'run.json').read_text())['plan']
    with sqlite3.connect(args.source) as db:
        network_km=db.execute('SELECT sum(length)/1000.0 FROM edges').fetchone()[0]
        source_meta=json.loads(db.execute("SELECT value FROM metadata WHERE k='complete'").fetchone()[0])
    report={'dataset':manifest['dataset'],'raw_blocks':len(parts),'raw_block_bytes':raw_bytes,
            'raw_block_gzip_bytes_measured':raw_gzip_bytes,'raw_gzip_trial_level':6,
            'analytical_rectangle_bytes':scores.size*4,'reachable_cells':reachable,
            'finite_zero_cells':zero_cells,
            'finite_cell_centers_checked_for_tile_coverage':reachable,
            'finest_tiles_required_by_finite_centers':len(required_keys),
            'missing_finite_center_tiles':len(missing_finite_tiles),
            'finite_center_coverage_check_seconds':coverage_check_seconds,
            'state_inside_cells':manifest['stats']['inside_cells'],
            'reachable_fraction_of_state_grid':reachable/manifest['stats']['inside_cells'],
            'bbox':manifest['bbox'],'area_km2_including_marine':plan['area_km2'],
            'walking_network_km_with_halo':network_km,
            'source_graph_nodes':source_meta['nodes'],'source_graph_edges':source_meta['edges'],'source_pois':source_meta['pois'],
            'by_zoom':by_zoom,'unique_png_payloads':len(unique_png),'unique_png_payload_bytes':sum(unique_png.values()),
            'finest_nontransparent_pixel_fraction':finest_pixels/(len(zoom_sizes[14])*256*256),
            'finest_occupied_tile_fraction_of_rectangle':len(zoom_sizes[14])/plan['tile_rectangle_counts']['14'],
            'metadata_json_bytes':sum(p.stat().st_size for p in site.rglob('*.json')),
            'manifest_bytes':(site/'manifest.json').stat().st_size,
            'raw_index_bytes':(data/'raw-index.json').stat().st_size,
            'coverage_geojson_bytes':(data/'coverage.geojson').stat().st_size,
            'tiles':len(actual),'hosted_files':len(assets),'hosted_bytes':sum(p.stat().st_size for p in assets),
            'largest_asset_bytes':max(p.stat().st_size for p in assets),'seconds':time.monotonic()-started}
    args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=='__main__':main()
