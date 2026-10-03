"""Checksummed, resumable block offsets for sorted PBFs; no global node map."""
import hashlib,json,time
from pathlib import Path
from scripts.pbf_node_scan import full_blocks


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def atomic(path,data):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(data));temp.replace(path)


def build(path,cache,expected_sha):
    path=Path(path);cache=Path(cache);started=time.monotonic()
    if sha(path)!=expected_sha:raise ValueError('Parent checksum differs')
    identity={'source_sha256':expected_sha,'source_bytes':path.stat().st_size,
              'code_sha256':sha(__file__),'scanner_sha256':sha(Path(__file__).with_name('pbf_node_scan.py'))}
    partial=cache.with_suffix('.partial.json')
    def checked(file):
        data=json.loads(file.read_text())
        if data['identity']!=identity:raise ValueError('Block index provenance changed')
        encoded=json.dumps(data['index'],separators=(',',':')).encode()
        if hashlib.sha256(encoded).hexdigest()!=data['index_sha256']:raise ValueError('Block index checksum differs')
        return data
    if cache.exists():return checked(cache)
    data=checked(partial) if partial.exists() else {'identity':identity,'offset':0,'blocks':0,'index':{'n':[],'w':[],'r':[]}}
    def save(target):
        data['index_sha256']=hashlib.sha256(json.dumps(data['index'],separators=(',',':')).encode()).hexdigest()
        atomic(target,data)
    for block,offset,end in full_blocks(path,start_offset=data['offset'],with_end_offsets=True):
        bounds={'n':[],'w':[],'r':[]}
        for group in block.groups:
            if group.HasField('dense') and len(group.dense.id):
                ids=group.dense.id
                if ids[0]<=0 or any(delta<=0 for delta in ids[1:]):raise ValueError('Unsorted dense node IDs')
                bounds['n'].extend([ids[0],sum(ids)])
            for kind,objects in [('n',group.nodes),('w',group.ways),('r',group.relations)]:
                if objects:
                    ids=[obj.id for obj in objects]
                    if any(a>=b for a,b in zip(ids,ids[1:])):raise ValueError('Unsorted object IDs')
                    bounds[kind].extend([ids[0],ids[-1]])
        for kind,ids in bounds.items():
            if ids:
                low,high=min(ids),max(ids);index=data['index'][kind]
                if index and index[-1][1]>=low:raise ValueError('Overlapping sorted block ranges')
                index.append([low,high,offset])
        data['offset']=end;data['blocks']+=1
        if data['blocks']%10000==0:
            save(partial)
            print(json.dumps({'block_index_blocks':data['blocks'],'bytes_read':end,'seconds':time.monotonic()-started}),flush=True)
    data['build_seconds']=time.monotonic()-started;save(cache)
    return data


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('cache',type=Path)
    parser.add_argument('--sha256',required=True);args=parser.parse_args()
    result=build(args.source,args.cache,args.sha256)
    print(json.dumps({'blocks':result['blocks'],'index_records':{k:len(v) for k,v in result['index'].items()},'seconds':result['build_seconds']}))
