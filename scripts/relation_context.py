"""Extract and independently audit complete relation geometry from a dated PBF."""
import json
from pathlib import Path
import numpy as np
import osmium
from shapely.geometry import Point,box
from pilot.source import TO_METERS,allowed_poi,permitted
from scripts.pbf_node_scan import selected_offsets,block_at,frame_at


def extract(parent,index,roots,output):
    parent=Path(parent);output=Path(output)
    if output.exists():raise FileExistsError(output)
    relations=set(roots);ways=set();nodes=set();processed=set()
    with parent.open('rb') as stream:
        while remaining:=relations-processed:
            found=set()
            for offset in selected_offsets(index['r'],remaining):
                for group in block_at(stream,offset).groups:
                    for relation in group.relations:
                        if relation.id not in remaining:continue
                        found.add(relation.id)
                        for kind,ref in zip(relation.types,np.cumsum(np.fromiter(relation.refs,dtype=np.int64))):
                            (nodes if kind==0 else ways if kind==1 else relations).add(int(ref))
            if found!=remaining:raise ValueError('Missing parent relation')
            processed.update(found)
            if len(relations)>10000:raise ValueError('Relation closure budget exceeded')
        found=set()
        for offset in selected_offsets(index['w'],ways):
            for group in block_at(stream,offset).groups:
                for way in group.ways:
                    if way.id in ways:
                        found.add(way.id);nodes.update(int(n) for n in np.cumsum(np.fromiter(way.refs,dtype=np.int64)))
        if found!=ways:raise ValueError('Missing parent way')
        if len(nodes)>1000000 or len(ways)>100000:raise ValueError('Relation geometry budget exceeded')
        offsets=selected_offsets(index['n'],nodes)|selected_offsets(index['w'],ways)|selected_offsets(index['r'],relations)
        original_header,_=frame_at(stream,0)
        with osmium.io.Reader(str(parent)) as reader:header=reader.header()
        temporary=output.with_suffix('.partial.osm.pbf')
        if temporary.exists():temporary.unlink()
        counts={'n':0,'w':0,'r':0}
        class Copy(osmium.SimpleHandler):
            def node(self,n):
                if n.id in nodes:writer.add_node(n);counts['n']+=1
            def way(self,w):
                if w.id in ways:writer.add_way(w);counts['w']+=1
            def relation(self,r):
                if r.id in relations:writer.add_relation(r);counts['r']+=1
        with osmium.SimpleWriter(str(temporary),header=header) as writer:
            copier=Copy()
            for offset in sorted(offsets):
                frame,_=frame_at(stream,offset)
                with osmium.io.Reader(osmium.io.FileBuffer(original_header+frame,'pbf')) as reader:osmium.apply(reader,copier)
        if counts!={'n':len(nodes),'w':len(ways),'r':len(relations)}:raise ValueError('Extract reference closure differs')
    temporary.replace(output)
    return counts


def audit(path,roots,expected_relations,support,config,existing_bounds=None):
    nodes={};ways={};relations={};bounds={};existing_bounds=existing_bounds or {}
    class Read(osmium.SimpleHandler):
        def node(self,n):
            if n.id in nodes:raise ValueError('Duplicate extracted node')
            nodes[n.id]=(n.location.lon,n.location.lat)
        def way(self,w):
            if w.id in ways:raise ValueError('Duplicate extracted way')
            ways[w.id]=[n.ref for n in w.nodes]
        def relation(self,r):
            if r.id in relations:raise ValueError('Duplicate extracted relation')
            relations[r.id]={'version':r.version,'members':[(m.type,m.ref) for m in r.members],'tags':dict(r.tags)}
    with osmium.io.Reader(str(path)) as reader:
        stamp=reader.header().get('osmosis_replication_timestamp');osmium.apply(reader,Read())
    for nid,(x,y) in nodes.items():bounds[f'n{nid}']=(x,y,x,y)
    for wid,refs in ways.items():
        if not refs or any(n not in nodes for n in refs):raise ValueError('Incomplete extracted way geometry')
        xy=np.array([nodes[n] for n in refs]);bounds[f'w{wid}']=(*xy.min(axis=0),*xy.max(axis=0))
    for key,value in existing_bounds.items():
        if key not in bounds or tuple(value)!=tuple(bounds[key]):raise ValueError('Completed geometry differs from retained member bounds')
    for rid,(version,members) in expected_relations.items():
        if rid not in relations or relations[rid]['version']!=version or relations[rid]['members']!=[tuple(m) for m in members]:
            raise ValueError('Parent relation version or members differ from import')
    memo={}
    def full(rid,stack=()):
        if rid in stack:raise ValueError('Cyclic relation geometry')
        if rid in memo:return memo[rid]
        if rid not in relations:raise ValueError('Missing nested relation')
        parts=[];node_ids=set()
        for kind,ref in relations[rid]['members']:
            if kind=='r':child,child_nodes=full(ref,(*stack,rid));parts.append(child);node_ids.update(child_nodes)
            else:
                key=f'{kind}{ref}'
                if key not in bounds:raise ValueError('Missing relation member')
                parts.append(bounds[key]);node_ids.update([ref] if kind=='n' else ways[ref])
        if not parts:raise ValueError('Empty relation')
        array=np.array(parts);result=(array[:,0].min(),array[:,1].min(),array[:,2].max(),array[:,3].max())
        memo[rid]=(result,node_ids);return memo[rid]
    results=[]
    for rid in roots:
        relation=relations[rid];tags=relation['tags']
        if not allowed_poi(tags,config) or not permitted(tags):raise ValueError('Parent POI classification differs')
        extent,node_ids=full(rid);w,s,e,n=extent;center=((w+e)/2,(s+n)/2)
        xy=np.array([nodes[nid] for nid in node_ids]);x,y=TO_METERS.transform(xy[:,0],xy[:,1])
        envelope=box(float(x.min()),float(y.min()),float(x.max()),float(y.max()))
        point=Point(*TO_METERS.transform(*center))
        # This narrowly scoped repair only excludes fully verified remote POIs.
        # Anything intersecting NY needs a graph/POI repair, never this shortcut.
        if support.intersects(envelope) or support.intersects(point):raise ValueError('Complete relation geometry may affect NY; graph repair required')
        results.append({'id':rid,'version':relation['version'],'name':tags.get('name'),
            'members':len(relation['members']),'geometry_nodes':len(node_ids),'bounds_wgs':list(extent),
            'representative_wgs':list(center),'representative_xy':[point.x,point.y],
            'geometry_distance_to_support_m':support.distance(envelope),
            'representative_distance_to_support_m':support.distance(point),
            'complete_geometry_outside_support':True})
    return {'timestamp':stamp,'counts':{'nodes':len(nodes),'ways':len(ways),'relations':len(relations)},'roots':results},bounds
