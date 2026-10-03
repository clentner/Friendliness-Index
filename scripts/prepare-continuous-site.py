"""Compose only shared display tiles; reuse both immutable analytical datasets."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import numpy as np
from PIL import Image
from shapely.geometry import shape,mapping
from shapely.ops import unary_union


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)}
            for p in root.rglob('*') if p.is_file()}


def compact(keys):
    rows=defaultdict(list)
    for key in keys:
        z,x,y=map(int,key.split('/'));rows[f'{z}/{y}'].append(x)
    result={}
    for key,values in sorted(rows.items()):
        ranges=[]
        for x in sorted(values):
            if ranges and x==ranges[-1]+1:ranges[-1]=x
            else:ranges.extend([x,x])
        result[key]=ranges
    return result


def select_pixels(ma,ny):
    # Copy one exact RGBA tuple, never source-over alpha blending.
    return np.where(ma[:,:,3:4]>0,ma,ny)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('build/ma-ny-continuous-final'))
    parser.add_argument('--report',type=Path,default=Path('qa-artifacts/continuous/preparation.json'))
    args=parser.parse_args();started=time.monotonic()
    assert not args.output.exists(),'Refusing to replace a staged site'
    roots={'ma':Path('build/massachusetts-pmtiles'),'ny':Path('build/new-york-pmtiles')}
    loose={'ma':Path('build/massachusetts'),'ny':Path('build/new-york-display')}
    manifests={key:json.loads((root/'manifest.json').read_text()) for key,root in roots.items()}
    originals={key:inventory(root) for key,root in roots.items()}
    keys={key:set(json.loads((root/'manifest.json').read_text())['available_tiles']) for key,root in loose.items()}
    assert manifests['ma']['metric_version']==manifests['ny']['metric_version']
    assert manifests['ma']['parameters']==manifests['ny']['parameters']
    for manifest in manifests.values():assert manifest['grid']['crs']=='EPSG:32619'
    identity={'source_manifests':{key:sha(root/'manifest.json') for key,root in roots.items()},
              'policy':'first-nontransparent-MA-then-NY-v1','builder_sha256':sha(__file__)}
    dataset=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    target=args.output;target.mkdir(parents=True)
    for key,root in roots.items():
        for source in (root/'datasets').rglob('*'):
            if not source.is_file():continue
            dest=target/source.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True)
            os.link(source,dest) if source.suffix=='.f32' else shutil.copy2(source,dest)
    shutil.copytree(roots['ma']/'vendor',target/'vendor')
    assert json.loads(Path('node_modules/proj4/package.json').read_text())['version']=='2.22.0'
    for source,name in [('node_modules/proj4/dist/proj4.js','proj4.js'),
                        ('node_modules/proj4/LICENSE.md','PROJ4-LICENSE.md'),
                        ('node_modules/mgrs/license.md','MGRS-LICENSE.md'),
                        ('node_modules/wkt-parser/LICENSE.md','WKT-PARSER-LICENSE.md')]:
        shutil.copy2(source,target/'vendor'/name)
    for name in ['app.js','continuous-data.js','style.css']:shutil.copy2(Path('web')/name,target/name)
    shutil.copy2(roots['ma']/'transparent.png',target/'transparent.png')
    shutil.copy2(roots['ma']/'_headers',target/'_headers')
    html=Path('web/index.html').read_text(encoding='utf-8').replace('Greater Boston','Massachusetts and New York').replace('Boston pilot','Massachusetts and New York map').replace('Boston','Massachusetts and New York')
    (target/'index.html').write_text(html,encoding='utf-8')
    immutable=target/'datasets'/dataset;immutable.mkdir()
    geometries=[shape(json.loads((roots[key]/manifests[key]['coverage_url']).read_text())['geometry']) for key in roots]
    coverage=unary_union(geometries)
    (immutable/'coverage.geojson').write_text(json.dumps({'type':'Feature','properties':{},'geometry':mapping(coverage)}))
    shared=keys['ma']&keys['ny'];composites={};pixel_proof={}
    def original(key,tile):
        return loose[key]/'datasets'/manifests[key]['dataset']/'tiles'/(tile+'.png')
    def save(tile,ma,ny):
        result=select_pixels(ma,ny)
        destination=immutable/'tiles'/(tile+'.png');destination.parent.mkdir(parents=True,exist_ok=True)
        Image.fromarray(result).save(destination,optimize=True)
        actual=np.array(Image.open(destination).convert('RGBA'))
        assert np.array_equal(actual,result)
        mask=ma[:,:,3]>0
        assert np.array_equal(actual[mask],ma[mask]) and np.array_equal(actual[~mask],ny[~mask])
        composites[tile]=destination.relative_to(target).as_posix()
        pixel_proof[tile]={'sha256':sha(destination),'bytes':destination.stat().st_size,
                          'both_nontransparent_pixels':int(((ma[:,:,3]>0)&(ny[:,:,3]>0)).sum())}
    for tile in sorted(shared):
        with Image.open(original('ma',tile)) as a,Image.open(original('ny',tile)) as b:
            save(tile,np.array(a.convert('RGBA')),np.array(b.convert('RGBA')))
    # MA has z7 as its minimum; derive only missing low overviews, no rescoring.
    current={tuple(map(int,tile.split('/')[1:])):Image.open(original('ma',tile)).convert('RGBA')
             for tile in keys['ma'] if tile.startswith('7/')}
    for z in [6,5]:
        following={}
        for x,y in sorted({(x//2,y//2) for x,y in current}):
            canvas=Image.new('RGBA',(512,512))
            for dx in range(2):
                for dy in range(2):
                    image=current.get((x*2+dx,y*2+dy))
                    if image is not None:canvas.paste(image,(dx*256,dy*256))
            ma=canvas.resize((256,256),Image.Resampling.LANCZOS);following[x,y]=ma
            tile=f'{z}/{x}/{y}';ny=np.zeros((256,256,4),dtype=np.uint8)
            if tile in keys['ny']:
                with Image.open(original('ny',tile)) as image:ny=np.array(image.convert('RGBA'))
            save(tile,np.array(ma),ny)
        for image in current.values():image.close()
        current=following
    for image in current.values():image.close()
    routing={'regions':{key:compact(values) for key,values in keys.items()},'composite':composites}
    # Expand every compact row and prove exact set equality before publication.
    for key,rows in routing['regions'].items():
        restored=set()
        for zy,segments in rows.items():
            z,y=zy.split('/')
            for i in range(0,len(segments),2):restored.update(f'{z}/{x}/{y}' for x in range(segments[i],segments[i+1]+1))
        assert restored==keys[key]
    (immutable/'routing.json').write_text(json.dumps(routing,separators=(',',':')))
    regions=[]
    for key,manifest in manifests.items():
        parts=manifest.get('archive_parts') or [{k:manifest[k] for k in ['minzoom','maxzoom','archive_url','archive_bytes','archive_sha256']}]
        regions.append({k:manifest[k] for k in ['dataset','area_label','bbox','grid','coverage_url','scores_sha256']}|{'id':key,'archive_parts':parts})
    manifest={'layout':'continuous-regions-v1','dataset':dataset,'area_label':'Massachusetts and New York',
              'bbox':list(coverage.bounds),'metric_version':manifests['ma']['metric_version'],
              'parameters':manifests['ma']['parameters'],'regions':regions,'minzoom':5,'maxzoom':14,
              'min_view_zoom':3,'coverage_url':f'datasets/{dataset}/coverage.geojson',
              'routing_url':f'datasets/{dataset}/routing.json','overlap_policy':identity['policy']}
    (target/'manifest.json').write_text(json.dumps(manifest))
    for key in roots:
        assert inventory(roots[key])==originals[key],'Source staging changed'
        for name,receipt in originals[key].items():
            if name.startswith('datasets/'):assert sha(target/name)==receipt['sha256']
    assets=inventory(target);total=sum(x['bytes'] for x in assets.values())
    baseline=sum(x['bytes'] for x in originals['ma'].values())
    assert len(assets)<20000 and max(x['bytes'] for x in assets.values())<25*1024**2
    old=json.loads(Path('qa-artifacts/ny/combined-site.json').read_text())
    report={'dataset':dataset,'output':str(target.resolve()),'identity':identity,'seconds':time.monotonic()-started,
            'files':len(assets),'served_assets':len(assets)-1,'bytes':total,
            'incremental_assets_vs_ma':len(assets)-len(originals['ma']),'incremental_bytes_vs_ma':total-baseline,
            'assets_change_vs_switcher':len(assets)-old['combined_upload_inputs'],'bytes_change_vs_switcher':total-old['combined_bytes'],
            'largest_asset_bytes':max(x['bytes'] for x in assets.values()),'shared_original_tiles':len(shared),
            'composite_tiles':len(composites),'composite_bytes':sum(x['bytes'] for x in pixel_proof.values()),
            'routing_bytes':(immutable/'routing.json').stat().st_size,'source_staging_unchanged':True,
            'raw_parts':sum(name.endswith('.f32') for name in assets),'r2_additional_bytes_vs_previous_plan':0,
            'changed_ma_assets':[name for name,receipt in originals['ma'].items() if assets.get(name)!=receipt],
            'unchanged_ma_assets':sum(assets.get(name)==receipt for name,receipt in originals['ma'].items()),
            'pixel_proof':pixel_proof,'assets':assets,'published':False}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in {'assets','pixel_proof'}}))


if __name__=='__main__':main()
