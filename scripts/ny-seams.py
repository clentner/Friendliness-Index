"""Independent real NY seam oracle, foreign destinations, and MA overlap."""
import json
import math
from pathlib import Path
import time
import numpy as np
from shapely import distance,points,intersects_xy
from shapely.geometry import box
from scipy.sparse.csgraph import dijkstra
from pilot import metric
from pilot.region import Grid,NY_SAMPLE_LOCATIONS
from pilot.regional_source import SpatialSource,boundary
from pilot.raster import DiskRaster
from pilot.source import TO_METERS,TO_WGS


def oracle(graph,queries,pois):
    qdist,qnode=metric.snap(graph.xy,queries);pdist,pnode=metric.snap(graph.xy,pois)
    expected=np.full(len(queries),np.nan);valid=np.isfinite(pdist)
    if not len(graph.xy):return expected
    matrix=graph.matrix()
    for i,(offset,node) in enumerate(zip(qdist,qnode)):
        if not np.isfinite(offset):continue
        lengths=dijkstra(matrix,directed=False,indices=node,limit=metric.RADIUS)
        total=lengths[pnode[valid]]+pdist[valid]+offset
        expected[i]=np.exp(-total[total<=metric.RADIUS]/metric.DECAY).sum()
    return expected


def halo_scores(source,queries):
    actual=np.full(len(queries),np.nan);keys=np.floor(queries/2000).astype(int)
    for key in np.unique(keys,axis=0):
        mask=np.all(keys==key,axis=1);lo=key*2000-metric.HALO;hi=(key+1)*2000+metric.HALO
        graph,pois=source.load((*lo,*hi))
        actual[mask],_=metric.score(graph,queries[mask],pois)
    return actual


def border(source,core,label,select):
    rows=source.db.execute('SELECT k,x,y FROM pois ORDER BY k').fetchall()
    xy=np.array([r[1:] for r in rows]);lon,lat=TO_WGS.transform(xy[:,0],xy[:,1])
    candidates=np.flatnonzero(select(lon,lat)&~intersects_xy(core,xy[:,0],xy[:,1]))
    candidates=candidates[np.argsort(distance(points(xy[candidates]),core))]
    for candidate in candidates[:60]:
        point=xy[candidate];graph,pois=source.load((*(point-2000),*(point+2000)),max_nodes=400000)
        inside=intersects_xy(core,graph.xy[:,0],graph.xy[:,1]);nearby=graph.xy[inside]
        if not len(nearby):continue
        nearby=nearby[np.argsort(np.linalg.norm(nearby-point,axis=1))[:100]]
        queries=np.unique(np.floor(nearby/25)*25+12.5,axis=0)
        queries=queries[intersects_xy(core,queries[:,0],queries[:,1])]
        queries=queries[np.argsort(np.linalg.norm(queries-point,axis=1))[:12]]
        if not len(queries) or np.linalg.norm(queries[0]-point)>650:continue
        full=oracle(graph,queries,pois)
        restricted=oracle(graph,queries,pois[intersects_xy(core,pois[:,0],pois[:,1])])
        delta=np.nan_to_num(full-restricted,nan=0)
        if delta.max()<=1e-8:continue
        actual=halo_scores(source,queries)
        np.testing.assert_allclose(actual,full,rtol=1e-10,atol=1e-10,equal_nan=True)
        return {'border':label,'candidate_poi':rows[candidate][0],
            'candidate_lonlat':[float(lon[candidate]),float(lat[candidate])],
            'ny_query_cells':len(queries),'reachable':int(np.isfinite(full).sum()),
            'max_cross_border_score_contribution':float(delta.max())}
    raise AssertionError('No cross-border contribution demonstrated: '+label)


def main():
    started=time.monotonic();source=SpatialSource('data/ny-20261001/source.sqlite')
    _,core=boundary('data/ny-20261001/boundary.json');results=[]
    for name,lon,lat in NY_SAMPLE_LOCATIONS:
        x,y=TO_METERS.transform(lon,lat);seam=round(x/2000)*2000;center=math.floor(y/25)*25+12.5
        queries=np.array([[seam+dx,center+dy] for dx in [-37.5,-12.5,12.5,37.5] for dy in [-50,0,50]])
        graph,pois=source.load((*(queries.min(axis=0)-2000),*(queries.max(axis=0)+2000)),max_nodes=400000)
        expected=oracle(graph,queries,pois);actual=halo_scores(source,queries)
        np.testing.assert_allclose(actual,expected,rtol=1e-10,atol=1e-10,equal_nan=True)
        finite=np.isfinite(expected)
        result={'location':name,'samples':len(queries),'reachable':int(finite.sum()),
            'reference_nodes':len(graph.xy),'max_error':float(np.max(np.abs(actual[finite]-expected[finite]))) if finite.any() else 0}
        results.append(result);print(json.dumps(result),flush=True)
    specs=[('Connecticut',lambda x,y:(x>-73.7)&(x<-73.4)&(y>41)&(y<42)),
        ('Massachusetts',lambda x,y:(x>-73.51)&(x<-73.25)&(y>42.1)&(y<42.7)),
        ('Vermont',lambda x,y:(x>-73.4)&(x<-73.1)&(y>43)&(y<44)),
        ('New Jersey',lambda x,y:(x>-74.5)&(x<-73.9)&(y>40.8)&(y<41.4)),
        ('Pennsylvania',lambda x,y:(x>-77)&(x<-75)&(y>41.8)&(y<42.01)),
        ('Ontario',lambda x,y:(x>-75.0)&(x<-74.5)&(y>44.9)&(y<45.04)),
        ('Quebec',lambda x,y:(x>-74.4)&(x<-73.3)&(y>45)&(y<45.05))]
    borders=[]
    for name,select in specs:
        result=border(source,core,name,select);borders.append(result);print(json.dumps(result),flush=True)
    # Compare actual published MA float32 cells close enough to NY that both
    # independent source support regions retain all contributing paths/POIs.
    ma_run=json.loads(Path('build/ma-run/run.json').read_text());p=ma_run['plan']
    ma_grid=Grid(tuple(p['grid_origin']),tuple(p['grid_shape']))
    ma_scores=DiskRaster('build/ma-run/scores.f32',ma_grid.shape)
    _,ma_core=boundary('data/ma-20261001/boundary.json');near=core.buffer(30);overlap=[]
    for job in ma_grid.jobs(ma_core):
        cx,cy,r0,r1,c0,c1=job
        if not near.intersects(box(cx*2000,cy*2000,(cx+1)*2000,(cy+1)*2000)):continue
        values=ma_scores[r0:r1,c0:c1].ravel();queries=ma_grid.queries(job)
        keep=np.isfinite(values)&(distance(points(queries),core)<=30)
        ids=np.flatnonzero(keep)
        if not len(ids):continue
        ids=ids[np.linspace(0,len(ids)-1,min(4,len(ids))).astype(int)]
        actual=halo_scores(source,queries[ids]);expected=values[ids]
        np.testing.assert_array_equal(actual.astype('<f4'),expected)
        overlap.append({'job':[cx,cy],'cells':len(ids),'float32_exact':True})
    assert sum(r['cells'] for r in overlap)>40,'Insufficient MA/NY overlap evidence'
    report={'seams':results,'cross_border_contributions':borders,'ma_overlap':overlap,
        'ma_overlap_cells':sum(r['cells'] for r in overlap),'seconds':time.monotonic()-started,
        'oracle':'Independent forward shortest paths versus grouped reverse halo scoring'}
    Path('qa-artifacts/ny/seams.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'complete':True,'ma_overlap_cells':report['ma_overlap_cells'],'seconds':report['seconds']}),flush=True)


if __name__=='__main__':main()
