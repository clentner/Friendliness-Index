"""Resumable Massachusetts build, with bounded disk-indexed scoring jobs."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import time
import numpy as np
from PIL import Image
from shapely import intersects_xy,intersects,box as vector_box
from shapely.geometry import box, mapping
from pilot import metric
from pilot.regional_source import SpatialSource, boundary
from pilot.tiles import sample_grid, colorize, tile_coordinate
from pilot.raster import DiskRaster

CHUNK=2000
SAMPLE_LOCATIONS=[('Boston',-71.06,42.356),('Worcester',-71.8,42.26),
                  ('Springfield',-72.58,42.1),('Pittsfield',-73.24,42.45),
                  ('Hyannis',-70.3,41.65),('Nantucket',-70.09,41.28),
                  ('Newburyport',-70.878,42.812),('Fall River',-71.15,41.7)]
NY_SAMPLE_LOCATIONS=[('Midtown',-73.985,40.758),('Brooklyn',-73.96,40.715),
    ('Queens',-73.83,40.76),('Bronx',-73.92,40.84),('Staten Island',-74.15,40.58),
    ('Hempstead',-73.62,40.706),('Montauk',-71.94,41.035),('Fishers Island',-72.018,41.263),
    ('Albany',-73.756,42.65),('Buffalo',-78.878,42.886),('Rochester',-77.61,43.156),
    ('Syracuse',-76.148,43.05),('Lake Placid',-73.98,44.28),('Adirondack wilderness',-74.3,44.0),
    ('Thousand Islands',-75.92,44.33),('Rouses Point',-73.36,44.99),
    ('NY MA border',-73.36,42.7)]


def region_label(root):
    code=json.loads((Path(root)/'boundary.json').read_text(encoding='utf-8'))['elements'][0]['tags']['ISO3166-2']
    return {'US-MA':'Massachusetts','US-NY':'New York State'}[code]


@dataclass(frozen=True)
class Grid:
    origin: tuple
    shape: tuple

    @classmethod
    def covering(cls,bounds):
        origin=np.floor(np.array(bounds[:2])/metric.SPACING)*metric.SPACING
        cols,rows=np.ceil((np.array(bounds[2:])-origin)/metric.SPACING).astype(int)
        return cls(tuple(origin), (int(rows),int(cols)))

    def jobs(self,core):
        x0,y0=self.origin;rows,cols=self.shape
        columns=np.arange(math.floor(x0/CHUNK),math.floor((x0+(cols-.5)*metric.SPACING)/CHUNK)+1)
        for cy in range(math.floor(y0/CHUNK),math.floor((y0+(rows-.5)*metric.SPACING)/CHUNK)+1):
            covered=intersects(core,vector_box(columns*CHUNK,cy*CHUNK,(columns+1)*CHUNK,(cy+1)*CHUNK))
            for column in columns[covered]:
                cx=int(column)
                c0=max(0,int((cx*CHUNK-x0)/metric.SPACING));c1=min(cols,int(((cx+1)*CHUNK-x0)/metric.SPACING))
                r0=max(0,int((cy*CHUNK-y0)/metric.SPACING));r1=min(rows,int(((cy+1)*CHUNK-y0)/metric.SPACING))
                yield cx,cy,r0,r1,c0,c1

    def queries(self,job):
        _,_,r0,r1,c0,c1=job
        x,y=np.meshgrid(self.origin[0]+(np.arange(c0,c1)+.5)*metric.SPACING,
                        self.origin[1]+(np.arange(r0,r1)+.5)*metric.SPACING)
        return np.column_stack([x.ravel(),y.ravel()])


def signature(source,root):
    code=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path('pilot').glob('*.py')))).hexdigest()
    config=hashlib.sha256(Path('poi_config.json').read_bytes()).hexdigest()
    if config!=source.metadata['poi_config_sha256']:raise ValueError('Source POI configuration changed; reindex')
    payload={'source':source.metadata,'code_sha256':code,'poi_config_sha256':config,
             'boundary_sha256':hashlib.sha256((Path(root)/'boundary.json').read_bytes()).hexdigest(),
             'metric_version':metric.VERSION,'chunk_m':CHUNK,'spacing_m':metric.SPACING}
    if payload['boundary_sha256']!=source.metadata['boundary_sha256']:raise ValueError('Boundary changed; reindex')
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),payload


def plan(root):
    wgs,core=boundary(Path(root)/'boundary.json');grid=Grid.covering(core.bounds)
    jobs=list(grid.jobs(core));tiles={}
    for z in range(7,15):
        w,s,e,n=wgs.bounds;x0,y0=tile_coordinate(w,n,z);x1,y1=tile_coordinate(e,s,z)
        tiles[z]=(math.floor(x1)-math.floor(x0)+1)*(math.floor(y1)-math.floor(y0)+1)
    return {'bbox':wgs.bounds,'crs':'EPSG:32619','grid_origin':grid.origin,'grid_shape':grid.shape,
            'cells_in_enclosing_rectangle':math.prod(grid.shape),'raw_disk_bytes':math.prod(grid.shape)*4,
            'area_km2':core.area/1e6,'scoring_jobs':len(jobs),'max_queries_per_job':int((CHUNK/metric.SPACING)**2),
            'halo_m':metric.HALO,'tile_rectangle_counts':tiles,'tile_rectangle_total':sum(tiles.values()),
            'scope':region_label(root)+' administrative area including islands; network context extends across borders'}


def score_region(root,index,destination,limit=None,sample=False):
    started=time.monotonic();destination=Path(destination);source=SpatialSource(index)
    sig,payload=signature(source,root)
    wgs,core=boundary(Path(root)/'boundary.json');grid=Grid.covering(core.bounds)
    destination.mkdir(parents=True,exist_ok=True);state_path=destination/'run.json'
    if state_path.exists():
        if json.loads(state_path.read_text())['signature']!=sig:raise ValueError('Checkpoint inputs/code changed; choose another run directory')
    else:
        state_path.write_text(json.dumps({'signature':sig,'provenance':payload,'plan':plan(root)},indent=2),encoding='utf-8')
    chunks=destination/'chunks';chunks.mkdir(exist_ok=True)
    jobs=list(grid.jobs(core))
    sample_names={}
    if sample:
        from pilot.source import TO_METERS
        locations=NY_SAMPLE_LOCATIONS if region_label(root)=='New York State' else SAMPLE_LOCATIONS
        sample_names={tuple(np.floor(np.array(TO_METERS.transform(lon,lat))/CHUNK).astype(int)):name
                      for name,lon,lat in locations}
        jobs=[j for j in jobs if j[:2] in sample_names]
        if len(jobs)!=len(locations):raise ValueError('Representative sampling locations are not unique covered jobs')
    finished=0;reused=0
    for job in jobs:
        cx,cy,r0,r1,c0,c1=job;target=chunks/f'{cx}-{cy}.npy';detail_path=target.with_suffix('.json')
        if target.exists() and detail_path.exists():
            detail=json.loads(detail_path.read_text())
            with target.open('rb') as f:valid=hashlib.file_digest(f,'sha256').hexdigest()==detail['sha256']
            if valid:reused+=1;continue
            raise ValueError(f'Checkpoint checksum mismatch: {target.name}')
        t=time.monotonic();queries=grid.queries(job);inside=intersects_xy(core,queries[:,0],queries[:,1])
        values=np.full(len(queries),np.nan,dtype='<f4')
        load_started=time.monotonic()
        graph,pois=source.load((cx*CHUNK-metric.HALO,cy*CHUNK-metric.HALO,(cx+1)*CHUNK+metric.HALO,(cy+1)*CHUNK+metric.HALO))
        load_seconds=time.monotonic()-load_started;score_started=time.monotonic()
        scored,stats=metric.score(graph,queries[inside],pois,deadline=t+120)
        values[inside]=scored;values=values.reshape(r1-r0,c1-c0)
        temp=target.with_suffix('.tmp')
        with temp.open('wb') as f:np.save(f,values,allow_pickle=False)
        with temp.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        temp.replace(target)
        detail={'job':job,'sha256':digest,'nodes':len(graph.xy),'pois':len(pois),'inside_cells':int(inside.sum()),
                'reachable':int(np.isfinite(values).sum()),'seconds':time.monotonic()-t,
                'load_seconds':load_seconds,'score_seconds':time.monotonic()-score_started,**stats}
        if job[:2] in sample_names:detail['location']=sample_names[job[:2]]
        detail_path.write_text(json.dumps(detail),encoding='utf-8');finished+=1
        if sample or finished%50==0:print(json.dumps({'finished':finished,'reused':reused,'total':len(jobs),'elapsed':round(time.monotonic()-started,1),'last':detail}),flush=True)
        if limit and finished>=limit:break
    result={'new_jobs':finished,'reused_jobs':reused,'target_jobs':len(jobs),'seconds':time.monotonic()-started,'sample':sample}
    print(json.dumps(result),flush=True);return result


def sparse_tiles(directory,scores,origin,bbox,progress=None,candidates=None):
    directory=Path(directory);w,s,e,n=bbox;x0,y0=tile_coordinate(w,n,14);x1,y1=tile_coordinate(e,s,14)
    available=[];current=set();pixels=np.arange(256)+.5;px,py=np.meshgrid(pixels,pixels)
    def restored(group):
        if progress is None:return None
        record=Path(progress)/(group+'.json')
        if not record.exists():return None
        entries=json.loads(record.read_text())
        for key,sha in entries.items():
            path=directory/(key+'.png')
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
                raise ValueError('Export checkpoint checksum mismatch: '+key)
        return list(entries)
    def checkpoint(group,keys):
        if progress is None:return
        record=Path(progress)/(group+'.json');record.parent.mkdir(parents=True,exist_ok=True)
        temp=record.with_suffix('.tmp')
        temp.write_text(json.dumps({key:hashlib.sha256((directory/(key+'.png')).read_bytes()).hexdigest() for key in keys}))
        temp.replace(record)
    def save(image,target):
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.tmp');image.save(temporary,format='PNG',optimize=True);temporary.replace(target)
    for tx in range(math.floor(x0),math.floor(x1)+1):
        previous=restored(f'x-{tx}')
        if previous is not None:
            available.extend(previous);current.update(tuple(map(int,k.split('/')[1:])) for k in previous);continue
        column=[]
        for ty in range(math.floor(y0),math.floor(y1)+1):
            if candidates is not None and (tx,ty) not in candidates:continue
            lon=(tx+px/256)/2**14*360-180
            lat=np.degrees(np.arctan(np.sinh(math.pi*(1-2*(ty+py/256)/2**14))))
            values=sample_grid(scores,origin,lon,lat)
            if not np.isfinite(values).any():continue
            target=directory/'14'/str(tx)/f'{ty}.png';target.parent.mkdir(parents=True,exist_ok=True)
            save(Image.fromarray(colorize(values)),target);current.add((tx,ty));column.append(f'14/{tx}/{ty}')
        available.extend(column);checkpoint(f'x-{tx}',column)
        if tx%10==0:print(json.dumps({'rendered_x':tx,'finest_tiles':len(current)}),flush=True)
    for z in range(13,6,-1):
        parents={(x//2,y//2) for x,y in current}
        previous=restored(f'z-{z}')
        if previous is not None:
            available.extend(previous);current=parents;continue
        level=[]
        for tx,ty in parents:
            canvas=Image.new('RGBA',(512,512))
            for dx in range(2):
                for dy in range(2):
                    child=directory/str(z+1)/str(tx*2+dx)/f'{ty*2+dy}.png'
                    if child.exists():
                        with Image.open(child) as image:canvas.paste(image,(dx*256,dy*256))
            target=directory/str(z)/str(tx)/f'{ty}.png';target.parent.mkdir(parents=True,exist_ok=True)
            save(canvas.resize((256,256),Image.Resampling.LANCZOS),target);level.append(f'{z}/{tx}/{ty}')
        available.extend(level);checkpoint(f'z-{z}',level)
        current=parents
    return sorted(available)


def block_tile_candidates(origin,row,col,shape):
    from pilot.source import TO_WGS
    x=origin[0]+col*metric.SPACING;y=origin[1]+row*metric.SPACING
    west,south,east,north=TO_WGS.transform_bounds(x,y,x+shape[1]*metric.SPACING,y+shape[0]*metric.SPACING,densify_pts=21)
    a,b=tile_coordinate(west,north,14);c,d=tile_coordinate(east,south,14)
    return {(tx,ty) for tx in range(math.floor(a)-1,math.floor(c)+2) for ty in range(math.floor(b)-1,math.floor(d)+2)}


def export_region(root,index,run,site,resume=False,archive_staging=False):
    started=time.monotonic();run=Path(run);site=Path(site);source=SpatialSource(index)
    sig,payload=signature(source,root)
    if json.loads((run/'run.json').read_text())['signature']!=sig:raise ValueError('Build provenance mismatch')
    if source.metadata['unresolved_relation_ids']:raise ValueError('Unresolved relation POIs require review before export')
    export_state=run/'export-state.json'
    identity={'signature':sig,'site':str(site.resolve()),'archive_staging':archive_staging}
    if site.exists():
        if not resume or (site/'manifest.json').exists():raise FileExistsError('Choose a new immutable export directory, or resume incomplete export')
        if not export_state.exists() or json.loads(export_state.read_text())!=identity:raise ValueError('Export checkpoint provenance changed')
    else:export_state.write_text(json.dumps(identity))
    wgs,core=boundary(Path(root)/'boundary.json');grid=Grid.covering(core.bounds);jobs=list(grid.jobs(core))
    for cx,cy,*_ in jobs:
        if not (run/'chunks'/f'{cx}-{cy}.json').exists():raise ValueError('Scoring incomplete')
    if shutil.disk_usage(run).free < math.prod(grid.shape)*12+20*1024**3:raise OSError('Insufficient disk headroom for raster and export')
    scores=DiskRaster(run/'scores.f32',grid.shape,create=True)
    stats={'jobs':len(jobs),'inside_cells':0,'reachable':0,'scoring_seconds':0,'max_chunk_nodes':0,'searches':0}
    for job in jobs:
        cx,cy,r0,r1,c0,c1=job;path=run/'chunks'/f'{cx}-{cy}.npy';detail=json.loads(path.with_suffix('.json').read_text())
        with path.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=detail['sha256']:raise ValueError('Checkpoint checksum mismatch')
        scores[r0:r1,c0:c1]=np.load(path,allow_pickle=False)
        for k in ('inside_cells','reachable','searches'):stats[k]+=detail[k]
        stats['scoring_seconds']+=detail['seconds'];stats['max_chunk_nodes']=max(stats['max_chunk_nodes'],detail['nodes'])
    scores.flush()
    with (run/'scores.f32').open('rb') as f:score_hash=hashlib.file_digest(f,'sha256').hexdigest()
    dataset=hashlib.sha256((sig+score_hash).encode()).hexdigest()[:16]
    data=site/'datasets'/dataset;data.mkdir(parents=True,exist_ok=True)
    assembled_seconds=time.monotonic()-started
    # Coarser raw partitions retain exact float32 cells without oversized assets.
    raw_parts=[];block=320;candidates=set()
    for row in range(0,grid.shape[0],block):
        for col in range(0,grid.shape[1],block):
            part=np.asarray(scores[row:row+block,col:col+block])
            if not np.isfinite(part).any():continue
            name=f'raw/{row}-{col}.f32';path=data/name;path.parent.mkdir(exist_ok=True);part.tofile(path)
            raw_parts.append({'row':row,'col':col,'shape':part.shape,'path':name,'sha256':hashlib.sha256(part.tobytes()).hexdigest()})
            # A conservative transformed block envelope, padded by a tile, only
            # skips tiles whose sampled cells cannot contain finite values.
            candidates.update(block_tile_candidates(grid.origin,row,col,part.shape))
    raw_seconds=time.monotonic()-started-assembled_seconds;tile_started=time.monotonic()
    available=sparse_tiles(data/'tiles',scores,grid.origin,wgs.bounds,run/'tile-progress',candidates)
    tile_seconds=time.monotonic()-tile_started
    (data/'raw-index.json').write_text(json.dumps({'dtype':'little-endian float32','nodata':'NaN','absent_blocks':'all NaN','parts':raw_parts}),encoding='utf-8')
    (data/'coverage.geojson').write_text(json.dumps({'type':'Feature','properties':{},'geometry':mapping(wgs)}),encoding='utf-8')
    Image.new('RGBA',(256,256)).save(site/'transparent.png')
    for name in ('index.html','app.js','style.css'):shutil.copy2(Path('web')/name,site/name)
    html=(site/'index.html').read_text(encoding='utf-8')
    label=region_label(root)
    (site/'index.html').write_text(html.replace('Greater Boston',label).replace('GREATER BOSTON',label.upper()).replace('Boston pilot',label+' map').replace('Boston',label),encoding='utf-8')
    shutil.copytree('web/vendor',site/'vendor',dirs_exist_ok=True);shutil.copy2('deploy/_headers',site/'_headers')
    meta={'dataset':dataset,'metric_version':metric.VERSION,'bbox':list(wgs.bounds),'area_label':label,
          'coverage_url':f'datasets/{dataset}/coverage.geojson','available_tiles':available,
          'generated_at':datetime.now(timezone.utc).isoformat(),'source':{'osm_timestamp':source.metadata['osm_timestamp'],'license':'ODbL-1.0','attribution':'© OpenStreetMap contributors','extracts':source.metadata['sources']},
          'code_sha256':payload['code_sha256'],'poi_config_sha256':payload['poi_config_sha256'],'scores_sha256':score_hash,
          'parameters':{'radius_m':metric.RADIUS,'lambda_m':metric.DECAY,'max_snap_m':metric.SNAP,'grid_spacing_m':metric.SPACING,'halo_m':metric.HALO,'display_max':metric.DISPLAY_MAX},
          'grid':{'crs':'EPSG:32619','origin_corner_m':grid.origin,'shape':grid.shape,'dtype':'little-endian float32','nodata':'NaN','raw_index_url':f'datasets/{dataset}/raw-index.json'},
          'tile_url':f'datasets/{dataset}/tiles/{{z}}/{{x}}/{{y}}.png','tiles':len(available),'minzoom':7,'maxzoom':14,'tile_size':256,'stats':stats}
    (data/'metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    manifest_bytes=json.dumps(meta).encode('utf-8')
    files=list(site.rglob('*'));files=[p for p in files if p.is_file()]
    limits={'files':len(files)+1,'bytes':sum(p.stat().st_size for p in files)+len(manifest_bytes),
            'largest_asset_bytes':max([p.stat().st_size for p in files]+[len(manifest_bytes)]),'export_seconds':time.monotonic()-started,
            'assembly_seconds':assembled_seconds,'raw_seconds':raw_seconds,'tile_seconds':tile_seconds,
            'candidate_finest_tiles':len(candidates),'archive_staging':archive_staging,
            'pages_ready':len(files)+1<=20000 and max([p.stat().st_size for p in files]+[len(manifest_bytes)])<=25*1024**2}
    if not archive_staging and not limits['pages_ready']:raise ValueError(f'Free Pages asset limits exceeded: {limits}; use explicit archive staging')
    (site/'manifest.json').write_bytes(manifest_bytes)
    (run/'export.json').write_text(json.dumps(limits,indent=2));print(json.dumps(limits),flush=True);return meta


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','score','export'])
    p.add_argument('--source-root',default='data/ma-20261001');p.add_argument('--index',default='data/ma-20261001/source.sqlite')
    p.add_argument('--run',default='build/ma-run');p.add_argument('--out',default='build/massachusetts');p.add_argument('--limit',type=int);p.add_argument('--sample',action='store_true')
    p.add_argument('--resume-export',action='store_true');p.add_argument('--archive-staging',action='store_true')
    a=p.parse_args()
    if a.action=='plan':print(json.dumps(plan(a.source_root),indent=2))
    elif a.action=='score':score_region(a.source_root,a.index,a.run,a.limit,a.sample)
    else:export_region(a.source_root,a.index,a.run,a.out,a.resume_export,a.archive_staging)

if __name__=='__main__':main()
