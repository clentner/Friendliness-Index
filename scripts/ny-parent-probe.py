"""Bounded range probe to estimate and timestamp-check the dated parent download."""
import json,time,struct
from pathlib import Path
from urllib.request import Request,urlopen
import osmium

url='https://download.geofabrik.de/north-america/us-261001.osm.pbf'
root=Path('data/ny-parent');root.mkdir(exist_ok=True)
started=time.monotonic()
with urlopen(Request(url,headers={'Range':'bytes=0-16777215','User-Agent':'FriendlinessIndex/2 source completeness'}),timeout=90) as response:
    if response.status!=206:raise ValueError('Parent server did not honor bounded range probe')
    size=int(response.headers['Content-Range'].split('/')[1]);raw=response.read(16777216+1)
assert len(raw)==16777216
(root/'us-261001.osm.pbf.part').write_bytes(raw)
header_length=struct.unpack('>I',raw[:4])[0]
# BlobHeader is a tiny protobuf: read only the data-size field.
def varint(data,i):
    value=0;shift=0
    while True:
        b=data[i];i+=1;value|=(b&127)<<shift
        if b<128:return value,i
        shift+=7
header=raw[4:4+header_length];i=0
while i<len(header):
    tag,i=varint(header,i)
    if tag&7==2:length,i=varint(header,i);i+=length
    elif tag&7==0:
        value,i=varint(header,i)
        if tag>>3==3:blob_size=value
    else:raise ValueError('Unexpected BlobHeader wire type')
with osmium.io.Reader(osmium.io.FileBuffer(raw[:4+header_length+blob_size],'pbf')) as reader:
    stamp=reader.header().get('osmosis_replication_timestamp')
assert stamp=='2026-10-01T20:22:06Z',stamp
seconds=time.monotonic()-started
report={'url':url,'total_bytes':size,'probe_bytes':len(raw),'probe_seconds':seconds,
    'probe_bytes_per_second':len(raw)/seconds,'linear_download_seconds_estimate':size*seconds/len(raw),
    'osm_timestamp':stamp,'additional_disk_reservation_bytes':25*1024**3}
Path('qa-artifacts/ny/parent-probe.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
