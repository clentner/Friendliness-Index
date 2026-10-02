"""Independent forward-search oracle for real regional halo seams and borders."""
import json
import math
from pathlib import Path
import time
import numpy as np
from shapely import intersects_xy,points,distance
from scipy.sparse.csgraph import dijkstra
from pilot import metric
from pilot.regional_source import SpatialSource,boundary
from pilot.source import TO_METERS,TO_WGS


def border_contribution(source,core,label,select):
    rows=source.db.execute('SELECT k,x,y FROM pois ORDER BY k').fetchall()
    xy=np.array([r[1:] for r in rows]);lon,lat=TO_WGS.transform(xy[:,0],xy[:,1])
    candidates=np.flatnonzero(select(lon,lat)&~intersects_xy(core,xy[:,0],xy[:,1]))
    gaps=distance(points(xy[candidates]),core)
    candidates=candidates[np.argsort(gaps)]
    for candidate in candidates[:30]:
        p=xy[candidate];reference,pois=source.load((* (p-2000),* (p+2000)),max_nodes=400000)
        interior=intersects_xy(core,reference.xy[:,0],reference.xy[:,1])
        nearby=reference.xy[interior]
        if not len(nearby):continue
        nearby=nearby[np.argsort(np.linalg.norm(nearby-p,axis=1))[:200]]
        queries=np.unique(np.floor(nearby/25)*25+12.5,axis=0)
        queries=queries[intersects_xy(core,queries[:,0],queries[:,1])]
        queries=queries[np.argsort(np.linalg.norm(queries-p,axis=1))[:12]]
        if not len(queries) or np.linalg.norm(queries[0]-p)>650:continue
        full,_=metric.score(reference,queries,pois)
        inside_pois=pois[intersects_xy(core,pois[:,0],pois[:,1])]
        restricted,_=metric.score(reference,queries,inside_pois)
        delta=np.nan_to_num(full-restricted,nan=0)
        if delta.max()<=1e-8:continue
        actual=np.full(len(queries),np.nan);keys=np.floor(queries/2000).astype(int)
        for key in np.unique(keys,axis=0):
            mask=np.all(keys==key,axis=1);lo=key*2000-metric.HALO;hi=(key+1)*2000+metric.HALO
            local,local_pois=source.load((*lo,*hi))
            actual[mask],_=metric.score(local,queries[mask],local_pois)
        np.testing.assert_allclose(actual,full,rtol=1e-10,atol=1e-10,equal_nan=True)
        result={'border':label,'candidate_poi':rows[candidate][0],
                'candidate_lonlat':[float(lon[candidate]),float(lat[candidate])],
                'ma_query_cells':len(queries),'reachable':int(np.isfinite(full).sum()),
                'max_cross_border_score_contribution':float(delta.max())}
        print(json.dumps(result),flush=True);return result
    raise AssertionError('No meaningful cross-border destination contribution found: '+label)


def main():
    started=time.monotonic();source=SpatialSource('data/ma-20261001/source.sqlite');results=[]
    locations=[('Boston',-71.06,42.356),('Worcester',-71.802,42.262),('Springfield',-72.588,42.102),
               ('Pittsfield',-73.245,42.451),('Nantucket',-70.099,41.284),('Vineyard',-70.602,41.456),
               ('CT-border',-72.58,42.002),('NH-border',-71.22,42.745)]
    for name,lon,lat in locations:
        x,y=TO_METERS.transform(lon,lat);seam=round(x/2000)*2000;center=math.floor(y/25)*25+12.5
        queries=np.array([[seam+dx,center+dy] for dx in [-37.5,-12.5,12.5,37.5] for dy in [-50,0,50]])
        low=queries.min(axis=0)-2000;high=queries.max(axis=0)+2000
        reference,pois=source.load((*low,*high),max_nodes=400000)
        if name=='CT-border':
            # The nominal seam falls in an unreachable river/floodplain here.
            # Anchor this border sample on an observed road instead.
            anchor=reference.xy[np.argmin(np.linalg.norm(reference.xy-[x,y],axis=1))]
            center_xy=np.floor(anchor/25)*25+12.5
            queries=np.array([center_xy+[dx,dy] for dx in [-25,0,25,50] for dy in [-25,0,25]])
            low=queries.min(axis=0)-2000;high=queries.max(axis=0)+2000
            reference,pois=source.load((*low,*high),max_nodes=400000)
        qdist,qnode=metric.snap(reference.xy,queries);pdist,pnode=metric.snap(reference.xy,pois)
        matrix=reference.matrix();expected=np.full(len(queries),np.nan)
        for i,(offset,node) in enumerate(zip(qdist,qnode)):
            if not np.isfinite(offset):continue
            distances=dijkstra(matrix,directed=False,indices=node,limit=metric.RADIUS)
            valid=np.isfinite(pdist)
            total=distances[pnode[valid]]+pdist[valid]+offset
            expected[i]=np.exp(-total[total<=metric.RADIUS]/metric.DECAY).sum()
        actual=np.full(len(queries),np.nan)
        keys=np.floor(queries/2000).astype(int)
        for key in np.unique(keys,axis=0):
            mask=np.all(keys==key,axis=1);lo=key*2000-metric.HALO;hi=(key+1)*2000+metric.HALO
            local,local_pois=source.load((*lo,*hi))
            actual[mask],_=metric.score(local,queries[mask],local_pois)
        np.testing.assert_allclose(actual,expected,rtol=1e-10,atol=1e-10,equal_nan=True)
        finite=np.isfinite(expected)
        assert finite.any(),name+' has no reachable samples'
        result={'location':name,'samples':len(queries),'reachable':int(finite.sum()),'reference_nodes':len(reference.xy),
                'max_error':float(np.max(np.abs(actual[finite]-expected[finite]))) if finite.any() else 0}
        results.append(result);print(json.dumps(result),flush=True)
    _,core=boundary('data/ma-20261001/boundary.json')
    borders=[border_contribution(source,core,'Connecticut',lambda lon,lat:(lon>-73.1)&(lon<-71.9)&(lat<42.05)),
             border_contribution(source,core,'New Hampshire',lambda lon,lat:(lon>-72.5)&(lon<-70.8)&(lat>42.69))]
    report={'results':results,'cross_border_contributions':borders,'seconds':time.monotonic()-started,'oracle':'Forward single-query shortest paths on an independent larger graph window'}
    Path('qa-artifacts/region-seams.json').write_text(json.dumps(report,indent=2));source.db.close()

if __name__=='__main__':main()
