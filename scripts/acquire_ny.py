"""Acquire dated New York and cross-border context without modifying MA caches."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from acquire_ma import fetch

ROOT = Path('data/ny-20261001')
SOURCES = [('us', name) for name in ['new-york', 'massachusetts', 'connecticut',
    'vermont', 'new-jersey', 'pennsylvania', 'rhode-island']] + [
    ('canada', 'ontario'), ('canada', 'quebec')]


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    boundary = ROOT / 'boundary.json'
    if not boundary.exists():
        query = '[out:json][timeout:180][date:"2026-10-01T20:22:06Z"];rel["boundary"="administrative"]["admin_level"="4"]["ISO3166-2"="US-NY"];out geom;'
        req = Request('https://overpass-api.de/api/interpreter',
            data=urlencode({'data': query}).encode(),
            headers={'User-Agent': 'FriendlinessIndex/2 New York boundary'})
        with urlopen(req, timeout=240) as response:
            raw = response.read(16*1024**2+1)
        data = json.loads(raw)
        if len(raw)>16*1024**2 or data.get('remark') or len(data.get('elements', [])) != 1:
            raise ValueError('Incomplete boundary response')
        boundary.write_bytes(raw)
        print(json.dumps({'boundary_bytes': len(raw)}), flush=True)
    records = []
    for country, name in SOURCES:
        started = time.monotonic()
        filename = name + '-261001.osm.pbf'
        base = f'https://download.geofabrik.de/north-america/{country}/'
        url = base + filename
        with urlopen(url+'.md5', timeout=60) as response:
            md5 = response.read(1024).decode().split()[0]
        cached = Path('data/ma-20261001') / filename
        dest = ROOT / filename
        reused = False
        if not dest.exists() and cached.exists():
            with cached.open('rb') as stream:
                if hashlib.file_digest(stream, 'md5').hexdigest() != md5:
                    raise ValueError('Cached source differs from provider')
            # Immutable source inputs; hard link avoids a duplicate half-GB NY PBF.
            os.link(cached, dest)
            reused = True
        if shutil.disk_usage(ROOT).free < 30*1024**3:
            raise OSError('Less than 30 GiB disk headroom before acquisition')
        fetch(url, dest, 3*1024**3, md5)
        poly = ROOT / (name+'.poly')
        fetch(base+name+'.poly', poly, 2*1024**2)
        with dest.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        record = {'path': filename, 'poly': poly.name, 'url': url,
            'bytes': dest.stat().st_size, 'md5': md5, 'sha256': sha,
            'poly_sha256': hashlib.sha256(poly.read_bytes()).hexdigest(),
            'reused_verified_cache': reused,
            'download_seconds': round(time.monotonic()-started, 3)}
        records.append(record)
        (ROOT/'sources.partial.json').write_text(json.dumps(records, indent=2))
        print(json.dumps(record), flush=True)
    (ROOT/'sources.partial.json').replace(ROOT/'sources.json')


if __name__ == '__main__':
    main()
