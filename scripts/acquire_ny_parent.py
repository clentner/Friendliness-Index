"""Download a checksum-verified dated parent after the bounded resource probe."""
import hashlib,json,shutil,time
from pathlib import Path
from urllib.request import urlopen
from acquire_ma import fetch

root=Path('data/ny-parent');root.mkdir(exist_ok=True)
probe=json.loads(Path('qa-artifacts/ny/parent-probe.json').read_text())
assert probe['osm_timestamp']=='2026-10-01T20:22:06Z'
assert probe['total_bytes']==12179450407
assert shutil.disk_usage(root).free>probe['total_bytes']+30*1024**3
url=probe['url'];started=time.monotonic()
with urlopen(url+'.md5',timeout=30) as response:md5=response.read(1024).decode().split()[0]
dest=root/'us-261001.osm.pbf'
fetch(url,dest,probe['total_bytes'],md5)
with dest.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
record={'path':str(dest),'url':url,'bytes':dest.stat().st_size,'md5':md5,'sha256':sha,'seconds':time.monotonic()-started}
(root/'parent.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
