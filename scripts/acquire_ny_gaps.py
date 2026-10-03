"""Dated complete-member metric extracts for provider gaps in Long Island Sound.

Overpass selects ways by nodes in an expanded bbox; this does not certify
arbitrary segments with both endpoints outside that bbox. Neighboring complete
way PBF extracts remain the primary crossing-edge source.
"""
import hashlib
import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError,URLError
import osmium
from shapely.geometry import shape
from shapely.ops import transform
from pilot.source import TO_WGS,acquisition_filter_hash

ROOT=Path('data/ny-20261001');STAMP='2026-10-01T20:22:06Z'


def main():
    config=json.loads(Path('poi_config.json').read_text())
    missing=shape(json.loads(Path('qa-artifacts/ny/missing-support.geojson').read_text()))
    parts=sorted(missing.geoms if hasattr(missing,'geoms') else [missing],key=lambda p:-p.area)
    records=json.loads((ROOT/'sources.json').read_text())
    records=[r for r in records if not r.get('supplemental')]
    for i,part in enumerate(parts):
        # 2 km beyond the measured gap, in addition to the existing support halo.
        w,s,e,n=transform(TO_WGS.transform,part.buffer(2000)).bounds
        bbox=f'{s},{w},{n},{e}'
        selectors=[f'way["highway"]({bbox});',f'node["barrier"]({bbox});']
        selectors += [f'nwr["{key}"]({bbox});' for key in config['allow']]
        query=f'[out:json][timeout:180][date:"{STAMP}"];('+''.join(selectors)+');(._;>>;);out meta;'
        name=f'sound-gap-{i}';raw_path=ROOT/(name+'.json');query_path=ROOT/(name+'.overpass')
        if not raw_path.exists():
            query_path.write_text(query,encoding='utf-8')
            for endpoint in ['https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter']:
                req=Request(endpoint,data=urlencode({'data':query}).encode(),
                    headers={'User-Agent':'FriendlinessIndex/2 source gap repair'})
                try:
                    with urlopen(req,timeout=240) as response:raw=response.read(200*1024**2+1)
                    print(json.dumps({'gap':i,'endpoint':endpoint,'response_bytes':len(raw)}),flush=True)
                    break
                except (HTTPError,URLError) as error:
                    print(json.dumps({'endpoint':endpoint,'error':str(error)}),flush=True)
            else:raise RuntimeError('Both public Overpass endpoints unavailable')
            data=json.loads(raw)
            if len(raw)>200*1024**2 or data.get('remark') or 'elements' not in data:
                raise ValueError('Partial gap extract rejected')
            raw_path.write_bytes(raw)
        data=json.loads(raw_path.read_bytes())
        if data.get('remark') or 'elements' not in data:raise ValueError('Partial cached response')
        if query_path.read_text(encoding='utf-8')!=query:raise ValueError('Gap query changed')
        filename=name+'-261001.osm.pbf';dest=ROOT/filename
        if not dest.exists():
            header=osmium.io.Header();header.set('osmosis_replication_timestamp',STAMP)
            temp=ROOT/(name+'.temporary.osm.pbf')
            if temp.exists():temp.unlink()
            with osmium.SimpleWriter(str(temp),header=header) as writer:
                elements=sorted(data['elements'],key=lambda e:({'node':0,'way':1,'relation':2}[e['type']],e['id']))
                for element in elements:
                    common={'id':element['id'],'version':element['version'],'tags':element.get('tags',{})}
                    if element['type']=='node':writer.add_node(osmium.osm.mutable.Node(**common,location=(element['lon'],element['lat'])))
                    elif element['type']=='way':writer.add_way(osmium.osm.mutable.Way(**common,nodes=element['nodes']))
                    else:writer.add_relation(osmium.osm.mutable.Relation(**common,members=[(m['type'][0],m['ref'],m.get('role','')) for m in element['members']]))
            temp.replace(dest)
        poly=ROOT/(name+'.poly')
        poly.write_text(f'{name}\n1\n {w} {s}\n {e} {s}\n {e} {n}\n {w} {n}\n {w} {s}\nEND\nEND\n')
        record={'path':filename,'poly':poly.name,'url':'https://overpass-api.de/api/interpreter',
            'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
            'poly_sha256':hashlib.sha256(poly.read_bytes()).hexdigest(),'supplemental':True,
            'query':query_path.name,'query_sha256':hashlib.sha256(query_path.read_bytes()).hexdigest(),
            'response':raw_path.name,'response_sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            'acquisition_poi_allow_sha256':acquisition_filter_hash(config),
            'bbox':[w,s,e,n],'elements':len(data['elements']),'requested_timestamp':STAMP}
        records.append(record);print(json.dumps(record),flush=True)
    temporary=ROOT/'sources.repaired.json';temporary.write_text(json.dumps(records,indent=2));temporary.replace(ROOT/'sources.json')


if __name__=='__main__':main()
