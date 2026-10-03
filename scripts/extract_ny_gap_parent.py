"""Bounded, reference-complete gap context from a verified dated parent PBF.

Select all nodes in the actual gap polygons buffered by 2 km; retain every
intersecting-node way and every POI relation touching that geometry, including
nested relations. pyosmium copies original objects and completes references.
No national coordinate index or national graph is constructed.
"""
import os
for key in ['OSMIUM_POOL_THREADS','OSMIUM_MAX_INPUT_QUEUE_SIZE','OSMIUM_MAX_OSMDATA_QUEUE_SIZE','OSMIUM_MAX_WORK_QUEUE_SIZE']:os.environ.setdefault(key,'2')
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import osmium
from shapely import intersects_xy,prepare
from shapely.geometry import shape,mapping
from shapely.ops import transform
from pilot.source import TO_METERS,TO_WGS,allowed_poi,permitted
from pbf_node_scan import scan,full_blocks,reference_arrays,in_sorted,selected_offsets,block_at,frame_at


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--parent',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--gaps',type=Path,default=Path('qa-artifacts/ny/missing-support.geojson'))
    parser.add_argument('--expected-sha');args=parser.parse_args();started=time.monotonic()
    if args.expected_sha and sha(args.parent)!=args.expected_sha:raise ValueError('Parent checksum mismatch')
    with osmium.io.Reader(str(args.parent)) as reader:header=reader.header()
    stamp=header.get('osmosis_replication_timestamp')
    if stamp!='2026-10-01T20:22:06Z':raise ValueError('Parent timestamp differs from MA')
    gap_path=args.gaps;gaps=shape(json.loads(gap_path.read_text()))
    context=gaps.buffer(2000);prepare(context);wgs=transform(TO_WGS.transform,context)
    bounds=[p.bounds for p in (wgs.geoms if hasattr(wgs,'geoms') else [wgs])]
    identity={'parent':str(args.parent.resolve()),'parent_bytes':args.parent.stat().st_size,
        'gap_sha256':sha(gap_path),'code_sha256':sha(__file__),'parent_sha256':args.expected_sha,
        'scanner_sha256':sha(Path(__file__).with_name('pbf_node_scan.py'))}
    cache=args.out.with_suffix('.selection.json')
    partial=cache.with_suffix('.partial.json')
    def save_selection(path,node_ids,stats):
        temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps({'identity':identity,'nodes':node_ids,'scan':stats,
            'nodes_sha256':hashlib.sha256(np.asarray(node_ids,dtype='<i8').tobytes()).hexdigest()}));temporary.replace(path)
    def read_selection(path):
        result=json.loads(path.read_text())
        if result['identity']!=identity:raise ValueError('Parent selection provenance changed')
        if hashlib.sha256(np.asarray(result['nodes'],dtype='<i8').tobytes()).hexdigest()!=result['nodes_sha256']:raise ValueError('Parent selection checksum mismatch')
        return result
    if cache.exists():
        selected=read_selection(cache)
        node_ids=selected['nodes'];node_stats=selected['scan']
    else:
        selected=read_selection(partial) if partial.exists() else {'nodes':[],'scan':{}}
        node_ids=selected['nodes']
        def accept(ids,lon,lat):
            x,y=TO_METERS.transform(lon,lat);mask=intersects_xy(context,x,y)
            for nid in ids[mask]:
                node_ids.append(int(nid))
        def progress(stats):
            save_selection(partial,node_ids,stats)
            print(json.dumps({'node_scan':stats}),flush=True)
        node_stats=scan(args.parent,bounds,accept,progress,resume=selected['scan'])
        save_selection(cache,node_ids,node_stats)
    print(json.dumps({'selected_context_nodes':len(node_ids),'node_seconds':node_stats['seconds']}),flush=True)
    if len(node_ids)>2000000:raise ValueError('Gap node budget exceeded')
    # libosmium IdTracker's sparse global-ID bitset exceeded the measured memory
    # guard. Sorted arrays + block-wise joins scale with selected objects instead.
    node_keys=np.array(sorted(node_ids),dtype=np.int64);way_ids=set();way_keys=None
    output_nodes=set(node_ids);node_index=[];way_index=[];relation_index=[]
    parents={};children={};reachable=set();poi_roots=set();edge_count=0
    config=json.loads(Path('poi_config.json').read_text())
    from itertools import chain
    for block_number,(block,offset) in enumerate(full_blocks(args.parent,with_offsets=True)):
        block_nodes=[];block_ways=[];block_relations=[]
        for group in block.groups:
            if group.HasField('dense') and len(group.dense.id):block_nodes.extend([group.dense.id[0],sum(group.dense.id)])
            if group.nodes:block_nodes.extend([group.nodes[0].id,group.nodes[-1].id])
            if group.ways:
                block_ways.extend([group.ways[0].id,group.ways[-1].id])
                if way_keys is not None:raise ValueError('Parent must be sorted nodes, ways, relations')
                refs,owners=reference_arrays(group.ways)
                for index in np.unique(owners[in_sorted(refs,node_keys)]):
                    way_ids.add(group.ways[int(index)].id)
                    output_nodes.update(int(ref) for ref in refs[owners==index])
                if len(way_ids)>300000:raise ValueError('Gap way budget exceeded')
            if group.relations:
                block_relations.extend([group.relations[0].id,group.relations[-1].id])
                if way_keys is None:
                    way_keys=np.array(sorted(way_ids),dtype=np.int64)
                    print(json.dumps({'selected_context_ways':len(way_ids),'seconds':time.monotonic()-started}),flush=True)
                refs,owners=reference_arrays(group.relations)
                types=np.fromiter(chain.from_iterable(r.types for r in group.relations),dtype=np.int8,count=len(refs))
                mask=((types==0)&in_sorted(refs,node_keys))|((types==1)&in_sorted(refs,way_keys))
                reachable.update(group.relations[int(i)].id for i in np.unique(owners[mask]))
                strings=block.strings.values
                for relation in group.relations:
                    tags={strings[k].decode():strings[v].decode() for k,v in zip(relation.keys,relation.vals)}
                    if allowed_poi(tags,config) and permitted(tags):poi_roots.add(relation.id)
                for ref,owner in zip(refs[types==2],owners[types==2]):
                    rid=group.relations[int(owner)].id;ref=int(ref)
                    parents.setdefault(ref,[]).append(rid);children.setdefault(rid,[]).append(ref);edge_count+=1
                    if edge_count>1000000:raise ValueError('Parent relation adjacency budget exceeded')
        for index,ids in [(node_index,block_nodes),(way_index,block_ways),(relation_index,block_relations)]:
            if ids:
                low,high=min(ids),max(ids)
                if index and low<=index[-1][1]:raise ValueError('Parent IDs must be sorted and unique within each type')
                index.append((low,high,offset))
        if block_number%10000==0:print(json.dumps({'reference_blocks':block_number,'selected_ways':len(way_ids),'seconds':time.monotonic()-started}),flush=True)
    pending=list(reachable)
    for rid in pending:
        for parent in parents.get(rid,[]):
            if parent not in reachable:reachable.add(parent);pending.append(parent)
    relation_ids=reachable&poi_roots;pending=list(relation_ids)
    for rid in pending:
        for child in children.get(rid,[]):
            if child not in relation_ids:relation_ids.add(child);pending.append(child)
    del parents,children,reachable,poi_roots
    initial_nodes=len(node_ids);node_ids=output_nodes;extra_ways=set()
    with args.parent.open('rb') as stream:
        for offset in selected_offsets(relation_index,relation_ids):
            for group in block_at(stream,offset).groups:
                for relation in group.relations:
                    if relation.id not in relation_ids:continue
                    refs=np.cumsum(np.fromiter(relation.refs,dtype=np.int64))
                    for kind,ref in zip(relation.types,refs):
                        ref=int(ref)
                        if kind==0:node_ids.add(ref)
                        elif kind==1:
                            if ref not in way_ids:extra_ways.add(ref)
                        else:assert ref in relation_ids,'Nested relation closure incomplete'
        for offset in selected_offsets(way_index,extra_ways):
            for group in block_at(stream,offset).groups:
                for way in group.ways:
                    if way.id in extra_ways:node_ids.update(int(ref) for ref in np.cumsum(np.fromiter(way.refs,dtype=np.int64)))
    way_ids.update(extra_ways)
    if len(node_ids)>3000000 or len(way_ids)>400000:raise ValueError('Reference completion exceeds bounded gap budget')
    if args.out.exists():raise FileExistsError('Refusing to replace a completed gap PBF')
    temp=args.out.with_name(args.out.stem+'.partial.osm.pbf')
    if temp.exists():temp.unlink()
    class Copy(osmium.SimpleHandler):
        def node(self,n):
            if n.id in node_ids:writer.add_node(n)
        def way(self,w):
            if w.id in way_ids:writer.add_way(w)
        def relation(self,r):
            if r.id in relation_ids:writer.add_relation(r)
    with osmium.SimpleWriter(str(temp),header=header) as writer:
        offsets=selected_offsets(node_index,node_ids)|selected_offsets(way_index,way_ids)|selected_offsets(relation_index,relation_ids)
        with args.parent.open('rb') as stream:
            original_header,_=frame_at(stream,0);copier=Copy()
            for offset in sorted(offsets):
                frame,_=frame_at(stream,offset)
                with osmium.io.Reader(osmium.io.FileBuffer(original_header+frame,'pbf')) as reader:osmium.apply(reader,copier)
    if temp.stat().st_size>300*1024**2:raise ValueError('Gap extract exceeds 300 MiB budget')
    temp.replace(args.out)
    poly=args.out.with_suffix('.poly');lines=['sound-context']
    for i,p in enumerate(wgs.geoms if hasattr(wgs,'geoms') else [wgs]):
        lines.extend([str(i+1),*[f' {x:.12f} {y:.12f}' for x,y in p.exterior.coords],'END'])
        for j,hole in enumerate(p.interiors):lines.extend([f'!{i+1}-{j}',*[f' {x:.12f} {y:.12f}' for x,y in hole.coords],'END'])
    poly.write_text('\n'.join(lines+['END'])+'\n')
    report={'parent':identity,'osm_timestamp':stamp,'initial_nodes':initial_nodes,
        'poi_config_sha256':sha('poi_config.json'),
        'nodes':len(node_ids),'ways':len(way_ids),'relations':len(relation_ids),
        'path':str(args.out),'bytes':args.out.stat().st_size,'sha256':sha(args.out),
        'poly':str(poly),'poly_sha256':sha(poly),'seconds':time.monotonic()-started,'node_scan':node_stats,
        'selection':'Nodes in measured missing polygons buffered by 2000 m; complete ways and POI relation members',
        'node_selector':'Bounded protobuf coordinate scan, objects independently decoded/copied by pyosmium'}
    args.report.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)


if __name__=='__main__':main()
