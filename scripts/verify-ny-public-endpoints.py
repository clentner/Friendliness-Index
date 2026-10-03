"""Read-only validation of published NY objects, including complete streamed hashes."""
import argparse,hashlib,json,time,urllib.request,socket,ipaddress
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--probe',action='store_true')
parser.add_argument('--part',action='append',choices=['overview','detail-z13','detail-z14'],help='Check only selected configured partition IDs')
parser.add_argument('--resolve-address',help='Verified public address; temporary client-only DNS override, TLS still validates hostname')
parser.add_argument('--resume',action='store_true',help='Reuse a previously verified full hash; repeat all header/range/CORS/cache checks')
args=parser.parse_args()
if args.resolve_address:
 ipaddress.ip_address(args.resolve_address)
 original_resolver=socket.getaddrinfo
 def resolve(host,*pos,**kw):return original_resolver(args.resolve_address if host=='tiles.chrislentner.com' else host,*pos,**kw)
 socket.getaddrinfo=resolve
config=json.loads(Path('deploy/ny-archives-ui300.json').read_text())
origins=[config['website_origin'],config['pages_origin']]
def request(url,method='GET',headers=None):
 return urllib.request.urlopen(urllib.request.Request(url,method=method,headers={'User-Agent':'Friendliness-Index-publication-QA',**(headers or {})}),timeout=120)
def headers(response):return {key.lower():value for key,value in response.headers.items()}
output=Path('qa-artifacts/continuous/public-endpoints-ui300.json')
previous=json.loads(output.read_text()) if output.exists() else {'objects':[]}
receipt={'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'objects':previous['objects'],'read_only':True,'dns_override':args.resolve_address,'checked_this_run':[]}
for part in config['archive_parts']:
 if args.part and part['id'] not in args.part:continue
 url=part['archive_url'];size=part['archive_bytes'];local=Path('build/archives')/part['archive_file']
 with request(url,'HEAD') as response:
  meta=headers(response);assert response.status==200
  assert int(meta['content-length'])==size,(url,meta)
  assert meta.get('etag'),(url,meta)
  assert not meta.get('content-encoding'),(url,meta)
 print(json.dumps({'ready':url,'bytes':size,'headers':meta}),flush=True)
 if args.probe:continue
 prior=next((obj for obj in previous['objects'] if obj['url']==url and obj['sha256']==part['archive_sha256']),None)
 if args.resume and prior:
  assert prior['head']['etag']==meta['etag'],'Object ETag changed; repeat full hash'
  obj={**prior,'head':meta,'ranges':[],'cors':[],'full_hash_reused':True}
 else:
  started=time.monotonic();digest=hashlib.sha256();count=0
  with request(url) as response:
   assert response.status==200
   assert response.headers.get('ETag')==meta['etag']
   while chunk:=response.read(1024*1024):digest.update(chunk);count+=len(chunk)
  assert count==size and digest.hexdigest()==part['archive_sha256'],(count,digest.hexdigest())
  obj={'url':url,'bytes':count,'sha256':digest.hexdigest(),'full_get_seconds':time.monotonic()-started,'head':meta,'ranges':[],'cors':[],'full_hash_dns_override':args.resolve_address}
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
 obj['verified_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 receipt['checked_this_run'].append(url)
 receipt['objects']=[item for item in receipt['objects'] if item['url']!=url]+[obj]
 output.write_text(json.dumps(receipt,indent=2))
 print(json.dumps({'verified':url,'full_hash':obj['sha256'],'seconds':obj['full_get_seconds'],'cache':cache.get('cf-cache-status')}),flush=True)
if not args.probe:
 receipt['passed']=set(receipt['checked_this_run'])=={p['archive_url'] for p in config['archive_parts']};receipt['completed_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 output.write_text(json.dumps(receipt,indent=2))
