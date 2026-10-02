"""Download dated public PBF inputs with checksums; no account or API keys."""
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path('data/ma-20261001')
BASE = 'https://download.geofabrik.de/north-america/us/'
STATES = ['massachusetts', 'connecticut', 'rhode-island', 'new-hampshire', 'vermont', 'new-york']


def fetch(url, dest, cap, expected=None):
    if dest.exists():
        raw_hash = hashlib.file_digest(dest.open('rb'), 'md5').hexdigest()
        if expected and raw_hash != expected:
            raise ValueError(f'Existing checksum mismatch: {dest}')
        return
    part = dest.with_suffix(dest.suffix+'.part')
    start = part.stat().st_size if part.exists() else 0
    headers = {'User-Agent': 'FriendlinessIndex/2 statewide research'}
    if start:
        headers['Range'] = f'bytes={start}-'
    with urlopen(Request(url, headers=headers), timeout=90) as response:
        append = start and response.status == 206
        size = start if append else 0
        length = int(response.headers.get('Content-Length', 0))
        if size+length > cap:
            raise ValueError('Download exceeds resource cap')
        with part.open('ab' if append else 'wb') as output:
            while block := response.read(1024*1024):
                size += len(block)
                if size > cap:
                    raise ValueError('Download exceeds resource cap')
                output.write(block)
    with part.open('rb') as handle:
        actual = hashlib.file_digest(handle, 'md5').hexdigest()
    if expected and actual != expected:
        raise ValueError(f'Checksum mismatch: {dest}')
    part.replace(dest)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    boundary = ROOT/'boundary.json'
    if not boundary.exists():
        query = '[out:json][timeout:90];rel["boundary"="administrative"]["admin_level"="4"]["ISO3166-2"="US-MA"];out geom;'
        request = Request('https://overpass-api.de/api/interpreter', data=urlencode({'data':query}).encode(),
                          headers={'User-Agent':'FriendlinessIndex/2 one administrative boundary'})
        with urlopen(request, timeout=120) as response:
            raw = response.read(8*1024*1024+1)
        data = json.loads(raw)
        if len(raw)>8*1024*1024 or data.get('remark') or len(data.get('elements',[])) != 1:
            raise ValueError('Incomplete or unexpected administrative boundary')
        boundary.write_bytes(raw)
        print(json.dumps({'boundary_bytes':len(raw)}),flush=True)
    records=[]
    for state in STATES:
        started=time.monotonic()
        name=state+'-261001.osm.pbf'
        url=BASE+name
        with urlopen(url+'.md5',timeout=30) as response:
            md5=response.read(1024).decode().split()[0]
        fetch(url,ROOT/name,2*1024**3,md5)
        fetch(BASE+state+'.poly',ROOT/(state+'.poly'),1024*1024)
        with (ROOT/name).open('rb') as handle:
            sha=hashlib.file_digest(handle,'sha256').hexdigest()
        record={'path':name,'url':url,'bytes':(ROOT/name).stat().st_size,'md5':md5,'sha256':sha,
                'download_seconds':round(time.monotonic()-started,3)}
        records.append(record)
        (ROOT/'sources.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        print(json.dumps(record),flush=True)


if __name__=='__main__':main()
