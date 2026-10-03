"""Independent pyproj/file-read oracle for the browser's raw score selection."""
import json
import math
from pathlib import Path
import struct
from pyproj import Transformer
from shapely.geometry import shape,Point
from shapely.ops import unary_union

root=Path('build/ma-ny-continuous-final');manifest=json.loads((root/'manifest.json').read_text())
coverage=shape(json.loads((root/manifest['coverage_url']).read_text())['geometry'])
forward=Transformer.from_crs(4326,32619,always_xy=True);inverse=Transformer.from_crs(32619,4326,always_xy=True)
indexes={r['id']:{(p['row'],p['col']):p for p in json.loads((root/r['grid']['raw_index_url']).read_text())['parts']} for r in manifest['regions']}
locations=[('Boston',-71.06,42.356),('Midtown',-73.985,40.758),('Buffalo',-78.878,42.886),
 ('Fishers',-72.018,41.263),('Montauk',-71.94,41.035),('Nantucket',-70.099,41.284),
 ('Adirondacks',-74.3,44),('Thousand-Islands',-75.92,44.33),('Pittsfield',-73.245,42.451),
 ('Rouses-Point',-73.36,44.99),('Hartford',-72.67,41.76),('Toronto',-79.38,43.65),('Atlantic',-70,40.5)]
# Include independent exact cell centers with zero, positive and NaN values.
for region in manifest['regions']:
    found=set()
    for part in indexes[region['id']].values():
        data=(root/region['grid']['raw_index_url']).parent/part['path']
        values=struct.iter_unpack('<f',data.read_bytes())
        for index,(value,) in enumerate(values):
            kind='nodata' if math.isnan(value) else 'zero' if value==0 else 'positive'
            if kind in found:continue
            row=part['row']+index//part['shape'][1];col=part['col']+index%part['shape'][1]
            ox,oy=region['grid']['origin_corner_m'];lon,lat=inverse.transform(ox+(col+.5)*25,oy+(row+.5)*25)
            if not coverage.covers(Point(lon,lat)):continue
            locations.append((region['id']+'-'+kind,lon,lat));found.add(kind)
            if len(found)==3:break
        if len(found)==3:break
    assert len(found)==3
# Border transects sample both datasets, exact boundary surroundings and gaps.
for lat in [42.1,42.35,42.6,42.72]:
    for lon in [-73.52,-73.48,-73.42,-73.36,-73.30,-73.24]:locations.append((f'border-{lon}-{lat}',lon,lat))
fixtures=[]
for name,lon,lat in locations:
    x,y=forward.transform(lon,lat);expected={'status':'outside','value':None,'dataset':None}
    if coverage.covers(Point(lon,lat)):
        expected={'status':'nodata','value':None,'dataset':None}
        for region in manifest['regions']:
            w,s,e,n=region['bbox']
            if not w<=lon<=e or not s<=lat<=n:continue
            ox,oy=region['grid']['origin_corner_m'];row=math.floor((y-oy)/25);col=math.floor((x-ox)/25)
            if not 0<=row<region['grid']['shape'][0] or not 0<=col<region['grid']['shape'][1]:continue
            part=indexes[region['id']].get((row//320*320,col//320*320))
            if not part:continue
            with ((root/region['grid']['raw_index_url']).parent/part['path']).open('rb') as stream:
                stream.seek(((row-part['row'])*part['shape'][1]+col-part['col'])*4)
                value=struct.unpack('<f',stream.read(4))[0]
            if math.isfinite(value):
                expected={'status':'value','value':value,'dataset':region['dataset'],'region':region['id'],'row':row,'col':col};break
    fixtures.append({'name':name,'lon':lon,'lat':lat,'projected':[x,y],'expected':expected})
target=Path('qa-artifacts/continuous/query-fixtures.json');target.write_text(json.dumps(fixtures,indent=2))
print(json.dumps({'fixtures':len(fixtures),'statuses':{s:sum(f['expected']['status']==s for f in fixtures) for s in ['value','nodata','outside']}}))
