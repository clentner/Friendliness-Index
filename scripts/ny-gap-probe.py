"""Small dated source probe; retain server errors for diagnosis."""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
import json,time

query='[out:json][timeout:30][date:"2026-10-01T20:22:06Z"];way[highway](41.27,-72.06,41.32,-71.99);out count;'
for endpoint in ['https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter']:
    started=time.monotonic()
    try:
        with urlopen(Request(endpoint,data=urlencode({'data':query}).encode(),
                headers={'User-Agent':'FriendlinessIndex/2 source verification'}),timeout=45) as r:
            body=r.read(10000).decode()
        report={'endpoint':endpoint,'seconds':time.monotonic()-started,'body':body}
        print(json.dumps(report),flush=True)
    except HTTPError as e:
        print(json.dumps({'endpoint':endpoint,'seconds':time.monotonic()-started,'error':str(e),'body':e.read(10000).decode(errors='replace')}),flush=True)
    except Exception as e:
        print(json.dumps({'endpoint':endpoint,'seconds':time.monotonic()-started,'error':str(e)}),flush=True)
