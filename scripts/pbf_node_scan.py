"""Bounded coordinate-only PBF scan using the official protobuf wire layout.

Field definitions: github.com/openstreetmap/OSM-binary/osmpbf/{fileformat,osmformat}.proto.
This selector never rewrites OSM objects: pyosmium independently reads selected
objects with their original versions/tags for the eventual supplemental PBF.
"""
import argparse
import json
from pathlib import Path
import struct
import time
import zlib
import numpy as np
from google.protobuf import descriptor_pb2,descriptor_pool,message_factory


def schema(full=False):
    spec=descriptor_pb2.FileDescriptorProto(name='coordinate_scan.proto',package='scan',syntax='proto2')
    def message(name,fields):
        definition=spec.message_type.add(name=name)
        for name,number,kind,repeated,target,default in fields:
            field=definition.field.add(name=name,number=number,type=kind,label=3 if repeated else 1)
            if target:field.type_name='.scan.'+target
            if default is not None:field.default_value=str(default)
    # Protobuf types: int32=5, int64=3, sint64=18, bytes=12, string=9, message=11.
    message('BlobHeader',[('type',1,9,False,None,None),('datasize',3,5,False,None,None)])
    message('Blob',[('raw',1,12,False,None,None),('raw_size',2,5,False,None,None),('zlib_data',3,12,False,None,None)])
    message('Node',[(n,i,18,False,None,None) for n,i in [('id',1),('lat',8),('lon',9)]])
    message('Dense',[(n,i,18,True,None,None) for n,i in [('id',1),('lat',8),('lon',9)]])
    group_fields=[('nodes',1,11,True,'Node',None),('dense',2,11,False,'Dense',None)]
    block_fields=[]
    if full:
        message('Strings',[('values',1,12,True,None,None)])
        message('Way',[('id',1,3,False,None,None),('refs',8,18,True,None,None)])
        message('Relation',[('id',1,3,False,None,None),('keys',2,13,True,None,None),('vals',3,13,True,None,None),
            ('refs',9,18,True,None,None),('types',10,5,True,None,None)])
        group_fields.extend([('ways',3,11,True,'Way',None),('relations',4,11,True,'Relation',None)])
        block_fields.append(('strings',1,11,False,'Strings',None))
    message('Group',group_fields)
    message('Block',block_fields+[('groups',2,11,True,'Group',None),('granularity',17,5,False,None,100),
        ('lat_offset',19,3,False,None,0),('lon_offset',20,3,False,None,0)])
    pool=descriptor_pool.DescriptorPool();pool.Add(spec)
    return {name:message_factory.GetMessageClass(pool.FindMessageTypeByName('scan.'+name))
        for name in ['BlobHeader','Blob','Block']}


MESSAGES=schema()
FULL_MESSAGES=schema(full=True)


def full_blocks(path,with_offsets=False,start_offset=0,with_end_offsets=False):
    """Yield one bounded block for reference selection; never keep a global graph."""
    with Path(path).open('rb') as stream:
        stream.seek(start_offset)
        while prefix:=stream.read(4):
            offset=stream.tell()-4
            if len(prefix)!=4:raise ValueError('Truncated PBF prefix')
            length=struct.unpack('>I',prefix)[0]
            if length>65536:raise ValueError('Oversized PBF header')
            header=MESSAGES['BlobHeader'].FromString(stream.read(length))
            if not 0<header.datasize<=32*1024**2:raise ValueError('Oversized PBF blob')
            data=stream.read(header.datasize)
            if len(data)!=header.datasize:raise ValueError('Truncated PBF blob')
            if header.type!='OSMData':continue
            blob=MESSAGES['Blob'].FromString(data)
            if blob.HasField('raw'):raw=blob.raw
            elif blob.HasField('zlib_data'):
                if not 0<blob.raw_size<=32*1024**2:raise ValueError('Oversized decompressed block')
                decoder=zlib.decompressobj();raw=decoder.decompress(blob.zlib_data,blob.raw_size+1)
                if len(raw)!=blob.raw_size or not decoder.eof or decoder.unconsumed_tail:raise ValueError('Invalid PBF block')
            else:raise ValueError('Unsupported compression')
            value=FULL_MESSAGES['Block'].FromString(raw)
            yield (value,offset,stream.tell()) if with_end_offsets else (value,offset) if with_offsets else value


def frame_at(stream,offset):
    stream.seek(offset);prefix=stream.read(4)
    length=struct.unpack('>I',prefix)[0]
    if length>65536:raise ValueError('Oversized block header')
    header_bytes=stream.read(length);header=MESSAGES['BlobHeader'].FromString(header_bytes)
    if not 0<header.datasize<=32*1024**2:raise ValueError('Oversized blob')
    data=stream.read(header.datasize)
    if len(data)!=header.datasize:raise ValueError('Truncated blob')
    return prefix+header_bytes+data,data


def block_at(stream,offset):
    _,data=frame_at(stream,offset);blob=MESSAGES['Blob'].FromString(data)
    if blob.HasField('raw'):raw=blob.raw
    elif blob.HasField('zlib_data'):
        if not 0<blob.raw_size<=32*1024**2:raise ValueError('Oversized block')
        decoder=zlib.decompressobj();raw=decoder.decompress(blob.zlib_data,blob.raw_size+1)
        if len(raw)!=blob.raw_size or not decoder.eof or decoder.unconsumed_tail:raise ValueError('Invalid block')
    else:raise ValueError('Unsupported compression')
    return FULL_MESSAGES['Block'].FromString(raw)


def selected_offsets(index,ids):
    """Locate sorted OSM IDs without an ID-addressed bitset or dense array."""
    from bisect import bisect_left
    ends=[high for low,high,offset in index];offsets=set()
    for oid in ids:
        i=bisect_left(ends,oid)
        if i==len(index) or index[i][0]>oid:raise ValueError(f'Parent reference missing: {oid}')
        offsets.add(index[i][2])
    return offsets


def reference_arrays(objects):
    from itertools import chain
    lengths=np.fromiter((len(o.refs) for o in objects),dtype=np.int64,count=len(objects))
    ends=np.cumsum(lengths);starts=ends-lengths
    deltas=np.fromiter(chain.from_iterable(o.refs for o in objects),dtype=np.int64,count=int(ends[-1]) if len(ends) else 0)
    cumulative=np.cumsum(deltas)
    offsets=np.zeros(len(starts),dtype=np.int64);nonempty=starts>0
    offsets[nonempty]=cumulative[starts[nonempty]-1]
    refs=cumulative-np.repeat(offsets,lengths)
    return refs,np.repeat(np.arange(len(objects)),lengths)


def in_sorted(values,keys):
    if not len(keys):return np.zeros(len(values),dtype=bool)
    positions=np.searchsorted(keys,values);valid=positions<len(keys)
    result=np.zeros(len(values),dtype=bool);result[valid]=keys[positions[valid]]==values[valid]
    return result


def scan(path,bboxes,on_selected,progress=None,resume=None):
    started=time.monotonic();resume=resume or {};nodes=resume.get('nodes',0);blocks=resume.get('blocks',0);selected=resume.get('selected',0)
    with Path(path).open('rb') as stream:
        stream.seek(resume.get('bytes_read',0))
        while prefix:=stream.read(4):
            if len(prefix)!=4:raise ValueError('Truncated PBF block prefix')
            length=struct.unpack('>I',prefix)[0]
            if length>65536:raise ValueError('Oversized PBF block header')
            header=MESSAGES['BlobHeader'].FromString(stream.read(length))
            if not 0<header.datasize<=32*1024**2:raise ValueError('Oversized PBF blob')
            data=stream.read(header.datasize)
            if len(data)!=header.datasize:raise ValueError('Truncated PBF blob')
            if header.type!='OSMData':continue
            blob=MESSAGES['Blob'].FromString(data)
            if blob.HasField('raw'):raw=blob.raw
            elif blob.HasField('zlib_data'):
                if not 0<blob.raw_size<=32*1024**2:raise ValueError('Oversized decompressed block')
                decoder=zlib.decompressobj();raw=decoder.decompress(blob.zlib_data,blob.raw_size+1)
                if len(raw)!=blob.raw_size or not decoder.eof or decoder.unconsumed_tail:raise ValueError('Invalid compressed block')
            else:raise ValueError('Unsupported PBF compression')
            block=MESSAGES['Block'].FromString(raw);blocks+=1
            for group in block.groups:
                if group.HasField('dense'):
                    dense=group.dense;count=len(dense.id);nodes+=count
                    if not (count==len(dense.lon)==len(dense.lat)):raise ValueError('PBF coordinate array mismatch')
                    lon=(np.cumsum(np.fromiter(dense.lon,dtype=np.int64,count=count))*block.granularity+block.lon_offset)*1e-9
                    lat=(np.cumsum(np.fromiter(dense.lat,dtype=np.int64,count=count))*block.granularity+block.lat_offset)*1e-9
                    mask=np.zeros(count,dtype=bool)
                    for w,s,e,n in bboxes:mask|=(lon>=w)&(lon<=e)&(lat>=s)&(lat<=n)
                    if mask.any():
                        ids=np.cumsum(np.fromiter(dense.id,dtype=np.int64,count=count))
                        on_selected(ids[mask],lon[mask],lat[mask]);selected+=int(mask.sum())
                for node in group.nodes:
                    nodes+=1;lon=(node.lon*block.granularity+block.lon_offset)*1e-9;lat=(node.lat*block.granularity+block.lat_offset)*1e-9
                    if any(w<=lon<=e and s<=lat<=n for w,s,e,n in bboxes):
                        on_selected(np.array([node.id]),np.array([lon]),np.array([lat]));selected+=1
            if progress and blocks%2000==0:progress({'blocks':blocks,'nodes':nodes,'selected':selected,'bytes_read':stream.tell(),'seconds':time.monotonic()-started})
    return {'nodes':nodes,'selected':selected,'blocks':blocks,'seconds':time.monotonic()-started,
        'resumed_from_byte':resume.get('bytes_read',0),'input_bytes':Path(path).stat().st_size}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('path');parser.add_argument('--report',required=True);args=parser.parse_args()
    result=scan(args.path,[(-73.68,40.94,-71.99,41.32)],lambda ids,x,y:None,lambda p:print(json.dumps(p),flush=True))
    Path(args.report).write_text(json.dumps(result,indent=2));print(json.dumps(result))
