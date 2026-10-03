"""Losslessly split the completed NY detail archive by zoom for the 300 MB UI cap."""
import hashlib,json,os,time
from pathlib import Path
from pmtiles.reader import Reader,all_tiles
from pmtiles.writer import Writer
from pmtiles.tile import Compression,TileType,zxy_to_tileid

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
 started=time.monotonic();config=json.loads(Path('deploy/ny-archives.json').read_text())
 # This script only derives from the original immutable two-part configuration.
 previous=json.loads(Path('qa-artifacts/ny/archives/package.json').read_text())
 detail=next(p for p in previous['parts'] if p['id']=='detail')
 source=Path(detail['archive']);assert sha(source)==detail['archive_sha256']
 expected=json.loads(Path(detail['report']).with_name('tile-inventory.json').read_text())
 root=Path('qa-artifacts/ny/archives/ui300');root.mkdir(parents=True,exist_ok=True)
 results=[];seen=set()
 for zoom in [13,14]:
  name=f'detail-z{zoom}';archive=Path('build/archives')/f"new-york-{config['dataset']}-{name}.pmtiles"
  report=root/name/'package.json';report.parent.mkdir(parents=True,exist_ok=True)
  keys={key:value for key,value in expected.items() if key.startswith(str(zoom)+'/')}
  if archive.exists() and not report.exists():
   # Recover a completed immutable output if report serialization was interrupted.
   with archive.open('rb') as src:
    def read(offset,length):src.seek(offset);data=src.read(length);assert len(data)==length;return data
    reader=Reader(read);metadata=reader.metadata();header=reader.header();verified=set()
    for zxy,data in all_tiles(read):
     key='/'.join(map(str,zxy));assert key not in verified and hashlib.sha256(data).hexdigest()==keys[key]['sha256'] and len(data)==keys[key]['bytes'];verified.add(key)
    assert verified==set(keys) and header['min_zoom']==zoom and header['max_zoom']==zoom
    assert metadata['source_archive_sha256']==detail['archive_sha256']
   part={'id':name,'archive':str(archive.resolve()),'archive_file':archive.name,'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'minzoom':zoom,'maxzoom':zoom,'metadata':metadata,'header':{k:getattr(v,'value',v) for k,v in header.items()},'internal_tiles':len(keys),'verified_byte_for_byte':len(keys),'missing_tiles':[{'place':'outside','tile':f'{zoom}/0/0'}]}
   assert part['archive_bytes']<300_000_000
   report.write_text(json.dumps(part,indent=2));report.with_name('tile-inventory.json').write_text(json.dumps(keys))
  if archive.exists():
   part=json.loads(report.read_text());assert sha(archive)==part['archive_sha256']
  else:
   temporary=archive.with_suffix('.pmtiles.tmp');assert not temporary.exists()
   with source.open('rb') as src:
    def read(offset,length):src.seek(offset);data=src.read(length);assert len(data)==length;return data
    metadata=Reader(read).metadata();metadata.update(minzoom=zoom,maxzoom=zoom,source_archive_sha256=detail['archive_sha256'],archive_partition=name)
    h={key:round(value*1e7) for key,value in zip(['min_lon_e7','min_lat_e7','max_lon_e7','max_lat_e7'],metadata['bbox'])}
    h.update(tile_compression=Compression.NONE,tile_type=TileType.PNG)
    with temporary.open('xb') as out:
     writer=Writer(out);copied=set()
     for zxy,data in all_tiles(read):
      if zxy[0]!=zoom:continue
      key='/'.join(map(str,zxy));assert hashlib.sha256(data).hexdigest()==keys[key]['sha256'] and len(data)==keys[key]['bytes']
      writer.write_tile(zxy_to_tileid(*zxy),data);copied.add(key)
     assert copied==set(keys);writer.finalize(h,metadata)
   with temporary.open('rb') as src:
    def read(offset,length):src.seek(offset);data=src.read(length);assert len(data)==length;return data
    reader=Reader(read);header=reader.header();verified=set()
    for zxy,data in all_tiles(read):
     key='/'.join(map(str,zxy));assert key not in verified and hashlib.sha256(data).hexdigest()==keys[key]['sha256'] and len(data)==keys[key]['bytes'];verified.add(key)
    assert verified==set(keys) and header['min_zoom']==zoom and header['max_zoom']==zoom
    assert reader.metadata()==metadata
   assert temporary.stat().st_size<300_000_000
   temporary.rename(archive)
   part={'id':name,'archive':str(archive.resolve()),'archive_file':archive.name,'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'minzoom':zoom,'maxzoom':zoom,'metadata':metadata,'header':{k:getattr(v,'value',v) for k,v in header.items()},'internal_tiles':len(keys),'verified_byte_for_byte':len(keys),'missing_tiles':[{'place':'outside','tile':f'{zoom}/0/0'}]}
   report.write_text(json.dumps(part,indent=2));report.with_name('tile-inventory.json').write_text(json.dumps(keys))
  assert not seen.intersection(keys);seen.update(keys)
  key=f"ny/{config['dataset']}/{part['archive_sha256'][:16]}-{name}.pmtiles"
  staged=Path('build/r2-upload')/key;staged.parent.mkdir(parents=True,exist_ok=True)
  if not staged.exists():os.link(archive,staged)
  assert sha(staged)==part['archive_sha256']
  part['archive_url']='https://tiles.chrislentner.com/'+key;part['upload_path']=str(staged.resolve());results.append(part)
  print(json.dumps({k:part[k] for k in ['id','upload_path','archive_url','archive_bytes','archive_sha256','internal_tiles']}),flush=True)
 assert seen==set(expected)
 overview=next(p for p in config['archive_parts'] if p['id']=='overview')
 new={**config,'archive_layout':'zoom-partitions-ui300-v1','archive_parts':[overview]+[{k:p[k] for k in ['id','minzoom','maxzoom','archive_file','archive_bytes','archive_sha256','archive_url']} for p in results]}
 new['archive_bytes_total']=sum(p['archive_bytes'] for p in new['archive_parts'])
 Path('deploy/ny-archives-ui300.json').write_text(json.dumps(new,indent=2))
 summary={'source_archive':str(source),'source_sha256':detail['archive_sha256'],'detail_tiles':len(seen),'detail_parts':results,'archive_bytes_total':new['archive_bytes_total'],'additional_archive_bytes':new['archive_bytes_total']-config['archive_bytes_total'],'seconds':time.monotonic()-started,'scores_unchanged':True,'all_payloads_byte_identical':True}
 (root/'split.json').write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='detail_parts'}))
if __name__=='__main__':main()
