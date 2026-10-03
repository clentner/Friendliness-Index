"""Exact OSM coordinates in a bounded, read-only disk page cache.

Keep complete way geometry. Filter ways before fetching coordinates; never clip
by endpoint presence. Native cache reuse requires full per-node PBF comparison.
"""
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import time
import numpy as np

DTYPE=np.dtype([('id','<i8'),('x','<i4'),('y','<i4')])
PAGE_ROWS=8192


def digest_prefix(path,length):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while length:
            block=stream.read(min(length,4*1024**2))
            if not block:raise ValueError('Truncated coordinate index')
            digest.update(block);length-=len(block)
    return digest.hexdigest()


def node_arrays(path):
    from scripts.pbf_node_scan import full_blocks
    for block in full_blocks(path):
        for group in block.groups:
            sets=[]
            if group.HasField('dense') and len(group.dense.id):
                dense=group.dense
                if not (len(dense.id)==len(dense.lon)==len(dense.lat)):raise ValueError('Coordinate array mismatch')
                sets.append((np.cumsum(np.fromiter(dense.id,dtype=np.int64)),
                    np.cumsum(np.fromiter(dense.lon,dtype=np.int64))*block.granularity+block.lon_offset,
                    np.cumsum(np.fromiter(dense.lat,dtype=np.int64))*block.granularity+block.lat_offset))
            if group.nodes:
                sets.append((np.array([n.id for n in group.nodes],dtype=np.int64),
                    np.array([n.lon for n in group.nodes],dtype=np.int64)*block.granularity+block.lon_offset,
                    np.array([n.lat for n in group.nodes],dtype=np.int64)*block.granularity+block.lat_offset))
            for ids,x,y in sets:
                # Reject unsupported sub-1e-7 precision instead of silently
                # changing libosmium's integer coordinate quantization.
                if np.any(x%100) or np.any(y%100):raise ValueError('PBF needs native sub-1e-7 coordinate handling')
                x=x//100;y=y//100
                if np.any(np.abs(x)>1800000000) or np.any(np.abs(y)>900000000):raise ValueError('Invalid node coordinate')
                rows=np.empty(len(ids),dtype=DTYPE);rows['id']=ids;rows['x']=x;rows['y']=y
                yield rows


def build_index(source,directory,source_sha256,reuse_native=None):
    source=Path(source);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    stem=source.name.removesuffix('.osm.pbf');meta=directory/(stem+'.nodes.json')
    target=directory/(stem+'.nodes.bin');started=time.monotonic()
    if meta.exists():
        data=json.loads(meta.read_text())
        if data['source_sha256']!=source_sha256 or data['format']!=1:raise ValueError('Coordinate cache source changed')
        if target.stat().st_size!=data['file_bytes'] or digest_prefix(target,data['rows']*16)!=data['payload_sha256']:
            raise ValueError('Coordinate cache checksum mismatch')
        return PagedLocations(target,data)
    if target.exists():raise FileExistsError('Unregistered coordinate index requires inspection: '+str(target))
    temporary=target.with_suffix('.partial');native=Path(reuse_native).open('rb') if reuse_native else None
    if temporary.exists():temporary.unlink()  # only this unregistered generated partial
    writer=None if native else temporary.open('xb');total=0;previous=0;fences=[];digest=hashlib.sha256()
    before=source.stat();blocks=0
    try:
        for rows in node_arrays(source):
            ids=rows['id']
            if ids[0]<=previous or np.any(ids[1:]<=ids[:-1]):raise ValueError('PBF node IDs must be positive, sorted and unique')
            for pos in range(PAGE_ROWS-1-total%PAGE_ROWS,len(rows),PAGE_ROWS):fences.append(int(ids[pos]))
            payload=rows.tobytes();digest.update(payload)
            if native:
                if native.read(len(payload))!=payload:raise ValueError('Native cache differs from original PBF coordinates')
            else:writer.write(payload)
            total+=len(rows);previous=int(ids[-1]);blocks+=1
            if blocks%2000==0:print(json.dumps({'coordinate_nodes':total,'seconds':round(time.monotonic()-started,2)}),flush=True)
        if not total:raise ValueError('Empty coordinate source')
        if total%PAGE_ROWS:fences.append(previous)
        after=source.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('PBF changed while indexing')
    finally:
        if native:native.close()
        if writer:writer.close()
    if reuse_native:os.link(Path(reuse_native),target)
    else:temporary.replace(target)
    data={'format':1,'source_sha256':source_sha256,'rows':total,'page_rows':PAGE_ROWS,
        'payload_sha256':digest.hexdigest(),'file_bytes':target.stat().st_size,'fences':fences,
        'native_cache_verified_every_node':bool(reuse_native),'build_seconds':time.monotonic()-started}
    interim=meta.with_suffix('.tmp');interim.write_text(json.dumps(data));interim.replace(meta)
    print(json.dumps({'coordinate_index':str(target),'rows':total,'native_equivalent':bool(reuse_native),
        'seconds':round(data['build_seconds'],2)}),flush=True)
    return PagedLocations(target,data)


class PagedLocations:
    def __init__(self,path,metadata,max_pages=256):
        if not 0<max_pages<=256:raise ValueError('Coordinate cache exceeds 32 MiB budget')
        self.path=Path(path);self.metadata=metadata;self.rows=metadata['rows'];self.page_rows=metadata['page_rows']
        self.fences=np.asarray(metadata['fences'],dtype=np.int64);self.stream=self.path.open('rb',buffering=0)
        if len(self.fences)!=(self.rows+self.page_rows-1)//self.page_rows or np.any(self.fences[1:]<=self.fences[:-1]):
            raise ValueError('Invalid coordinate page fences')
        self.pages=OrderedDict();self.max_pages=max_pages;self.hits=0;self.misses=0;self.bytes_read=0

    def page(self,number):
        if number in self.pages:
            self.hits+=1;self.pages.move_to_end(number);return self.pages[number]
        count=min(self.page_rows,self.rows-number*self.page_rows)
        self.stream.seek(number*self.page_rows*16);raw=self.stream.read(count*16)
        if len(raw)!=count*16:raise ValueError('Truncated coordinate page')
        rows=np.frombuffer(raw,dtype=DTYPE)
        if rows['id'][-1]!=self.fences[number]:raise ValueError('Coordinate fence mismatch')
        if len(self.pages)>=self.max_pages:self.pages.popitem(last=False)
        self.pages[number]=rows;self.misses+=1;self.bytes_read+=len(raw)
        return rows

    def ticks(self,ids,allow_missing=False):
        ids=np.asarray(ids,dtype=np.int64);output=np.zeros((len(ids),2),dtype='<i4');found=np.zeros(len(ids),dtype=bool)
        numbers=np.searchsorted(self.fences,ids)
        for number in np.unique(numbers[numbers<len(self.fences)]):
            selected=np.flatnonzero(numbers==number);page=self.page(int(number));positions=np.searchsorted(page['id'],ids[selected])
            valid=positions<len(page);matched=selected[valid];positions=positions[valid]
            valid=page['id'][positions]==ids[matched];matched=matched[valid];positions=positions[valid]
            output[matched,0]=page['x'][positions];output[matched,1]=page['y'][positions];found[matched]=True
        if not allow_missing and not found.all():raise KeyError('Missing source node: '+str(int(ids[np.flatnonzero(~found)[0]])))
        return output,found

    def lookup(self,ids):
        ticks,_=self.ticks(ids);xy=ticks.astype(np.float64)/10000000.0
        return xy[:,0],xy[:,1]

    def stats(self):
        return {'resident_cache_bytes':sum(p.nbytes for p in self.pages.values()),'cache_limit_bytes':self.max_pages*self.page_rows*16,
                'fence_bytes':self.fences.nbytes,'page_hits':self.hits,'page_misses':self.misses,'read_bytes':self.bytes_read}

    def used_memory(self):
        return self.rows*16

    def close(self):
        self.pages.clear();self.stream.close()
