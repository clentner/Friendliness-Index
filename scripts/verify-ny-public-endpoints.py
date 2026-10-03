"""Read-only validation of published NY objects, including complete streamed hashes."""
import argparse,hashlib,json,time,urllib.request
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--probe',action='store_true')
args=parser.parse_args()
config=json.loads(Path('deploy/ny-archives-ui300.json').read_text())
origins=[config['website_origin'],config['pages_origin']]
def request(url,method='GET',headers=None):
 return urllib.request.urlopen(urllib.request.Request(url,method=method,headers={'User-Agent':'Friendliness-Index-publication-QA',**(headers or {})}),timeout=120)
def headers(response):return {key.lower():value for key,value in response.headers.items()}
receipt={'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'objects':[],'read_only':True}
for part in config['archive_parts']:
 url=part['archive_url'];size=part['archive_bytes'];local=Path('build/archives')/part['archive_file']
 with request(url,'HEAD') as response:
  meta=headers(response);assert response.status==200
  assert int(meta['content-length'])==size,(url,meta)
  assert meta.get('etag'),(url,meta)
  assert not meta.get('content-encoding'),(url,meta)
 print(json.dumps({'ready':url,'bytes':size,'headers':meta}),flush=True)
 if args.probe:continue
 started=time.monotonic();digest=hashlib.sha256();count=0
 with request(url) as response:
  assert response.status==200
  assert response.headers.get('ETag')==meta['etag']
  while chunk:=response.read(1024*1024):digest.update(chunk);count+=len(chunk)
 assert count==size and digest.hexdigest()==part['archive_sha256'],(count,digest.hexdigest())
 obj={'url':url,'bytes':count,'sha256':digest.hexdigest(),'full_get_seconds':time.monotonic()-started,'head':meta,'ranges':[],'cors':[]}
 for start,length in [(0,127),(16384,4096),(size//2,4096),(size-4096,4096)]:
  end=start+length-1
  with request(url,headers={'Range':f'bytes={start}-{end}'}) as response:
   actual=response.read();h=headers(response)
   assert response.status==206 and h['content-range']==f'bytes {start}-{end}/{size}'
   assert len(actual)==length and h['etag']==meta['etag']
  with local.open('rb') as f:f.seek(start);expected=f.read(length)
  assert actual==expected
  obj['ranges'].append({'start':start,'bytes':length,'status':206,'sha256':hashlib.sha256(actual).hexdigest(),'headers':h})
 for origin in origins:
  with request(url,headers={'Origin':origin,'Range':'bytes=0-126'}) as response:
   actual=response.read();h=headers(response)
   assert response.status==206 and len(actual)==127
   assert h.get('access-control-allow-origin') in [origin,'*'],(origin,h)
   exposed={x.strip().lower() for x in h.get('access-control-expose-headers','').split(',')}
   assert {'etag','content-range','accept-ranges','content-length'}<=exposed or '*' in exposed,(origin,h)
   assert h['etag']==meta['etag']
  with request(url,'HEAD',{'Origin':origin}) as response:
   assert response.status==200 and response.headers.get('Access-Control-Allow-Origin') in [origin,'*']
  obj['cors'].append({'origin':origin,'headers':h,'get_and_head':True})
 for attempt in range(3):
  with request(url,headers={'Range':'bytes=0-126'}) as response:
   response.read();cache=headers(response)
  if cache.get('cf-cache-status')=='HIT':break
  time.sleep(2)
 assert cache.get('cf-cache-status')=='HIT',(url,cache)
 obj['cache_hit']=cache
 receipt['objects'].append(obj)
 Path('qa-artifacts/continuous/public-endpoints.json').write_text(json.dumps(receipt,indent=2))
 print(json.dumps({'verified':url,'full_hash':digest.hexdigest(),'seconds':obj['full_get_seconds'],'cache':cache.get('cf-cache-status')}),flush=True)
if not args.probe:
 receipt['passed']=True;receipt['completed_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 Path('qa-artifacts/continuous/public-endpoints.json').write_text(json.dumps(receipt,indent=2))
