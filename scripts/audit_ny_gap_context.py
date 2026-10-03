"""Inspect dated context for coastline, island, walking and POI evidence at gaps."""
import argparse,json,time
from pathlib import Path
import numpy as np
import osmium
from shapely.geometry import shape,LineString,Point
from shapely.ops import unary_union,transform
from pilot.source import TO_METERS,TO_WGS,walking,allowed_poi,permitted,representative

parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('--report',required=True);args=parser.parse_args()
started=time.monotonic();gaps=shape(json.loads(Path('qa-artifacts/ny/missing-support.geojson').read_text()))
parts=list(gaps.geoms);config=json.loads(Path('poi_config.json').read_text())
nodes={};way_bounds={};relations={};roads=[];coasts=[];pois=[];islands=[];water=[];inside_nodes=[]
class Audit(osmium.SimpleHandler):
    def node(self,n):
        lon,lat=n.location.lon,n.location.lat;nodes[n.id]=(lon,lat);tags=dict(n.tags)
        point=Point(*TO_METERS.transform(lon,lat))
        if gaps.intersects(point):inside_nodes.append({'id':n.id,'tags':tags,'lonlat':[lon,lat]})
        if allowed_poi(tags,config) and permitted(tags):pois.append((f'n{n.id}',point))
        if tags.get('place') in ('island','islet'):islands.append((f'n{n.id}',point))
        if tags.get('natural') in ('water','bay','strait','sea') or tags.get('place')=='sea':water.append((f'n{n.id}',point))
    def way(self,w):
        coords=np.array([nodes[n.ref] for n in w.nodes]);tags=dict(w.tags)
        if not len(coords):return
        way_bounds[w.id]=(*coords.min(axis=0),*coords.max(axis=0))
        if len(coords)>1:
            x,y=TO_METERS.transform(coords[:,0],coords[:,1]);line=LineString(np.column_stack([x,y]))
            if walking(tags):roads.append((w.id,line))
            if tags.get('natural')=='coastline':coasts.append((w.id,line))
            if tags.get('place') in ('island','islet'):islands.append((f'w{w.id}',line))
            if tags.get('natural') in ('water','bay','strait','sea'):water.append((f'w{w.id}',line))
        if allowed_poi(tags,config) and permitted(tags):
            p=representative({'type':'way','geometry':[{'lon':lon,'lat':lat} for lon,lat in coords]})
            if p is not None:pois.append((f'w{w.id}',Point(*p)))
    def relation(self,r):relations[r.id]=([(m.type,m.ref) for m in r.members],dict(r.tags))
Audit().apply_file(args.source)
memo={}
def bounds(rid,stack=()):
    if rid in memo:return memo[rid]
    if rid in stack:return None
    all_bounds=[]
    for kind,ref in relations[rid][0]:
        b=(*nodes[ref],*nodes[ref]) if kind=='n' else way_bounds[ref] if kind=='w' else bounds(ref,(*stack,rid))
        if b is None:return None
        all_bounds.append(b)
    if not all_bounds:return None
    a=np.array(all_bounds);memo[rid]=(a[:,0].min(),a[:,1].min(),a[:,2].max(),a[:,3].max());return memo[rid]
for rid,(_,tags) in relations.items():
    if allowed_poi(tags,config) and permitted(tags):
        b=bounds(rid)
        if b is not None:w,s,e,n=b;pois.append((f'r{rid}',Point(*TO_METERS.transform((w+e)/2,(s+n)/2))))
results=[]
for i,gap in enumerate(parts):
    def inspect(features):
        return {'intersecting_ids':[key for key,geometry in features if gap.intersects(geometry)],
            'nearest_m':min((gap.distance(geometry) for _,geometry in features),default=None)}
    results.append({'gap':i,'area_m2':gap.area,'bbox_wgs84':transform(TO_WGS.transform,gap).bounds,
        'walking':inspect(roads),'pois':inspect(pois),'coastline':inspect(coasts),
        'islands':inspect(islands),'water_features':inspect(water)})
report={'source':args.source,'gaps':results,'nodes_inside_missing_area':inside_nodes,
    'context_counts':{'nodes':len(nodes),'ways':len(way_bounds),'relations':len(relations),
        'walking_ways':len(roads),'coastline_ways':len(coasts),'pois':len(pois)},
    'seconds':time.monotonic()-started,
    'interpretation':'OSM evidence at the dated snapshot; absence of mapped roads is not a general claim about real-world accessibility.'}
Path(args.report).write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='nodes_inside_missing_area'}))
