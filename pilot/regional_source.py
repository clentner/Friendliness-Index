"""Stream PBFs into a disk spatial index; load only one scoring halo at a time."""
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
import gc
import uuid
import numpy as np
import osmium
from shapely import prepare
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize_full, unary_union, transform
from pilot import metric
from pilot.source import TO_METERS, TO_WGS, allowed_poi, permitted, walking, representative


def boundary(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    relation=data['elements'][0]
    if relation.get('tags',{}).get('ISO3166-2')!='US-MA':
        raise ValueError('Expected Massachusetts administrative boundary')
    rings={}
    for role in ('outer','inner'):
        lines=[LineString([(p['lon'],p['lat']) for p in m['geometry']])
               for m in relation['members'] if m.get('role')==role and m.get('geometry')]
        polygons,cuts,dangles,invalid=polygonize_full(unary_union(lines))
        if not cuts.is_empty or not dangles.is_empty or not invalid.is_empty:
            raise ValueError('Administrative boundary contains incomplete rings')
        rings[role]=unary_union(polygons)
    result=rings['outer'].difference(rings['inner'])
    if result.is_empty or not result.is_valid:
        raise ValueError('Incomplete Massachusetts boundary geometry')
    projected=transform(TO_METERS.transform,result)
    prepare(projected)
    return result, projected


def read_poly(path):
    rings=[];holes=[];points=[];inner=False
    for line in Path(path).read_text().splitlines()[1:]:
        parts=line.split()
        if len(parts)==2:
            points.append(tuple(map(float,parts)))
        elif line.strip()=='END' and points:
            (holes if inner else rings).append(Polygon(points));points=[]
        elif parts and parts[0]!='END':
            inner=parts[0].startswith('!')
    return unary_union(rings).difference(unary_union(holes))


def connect(path):
    db=sqlite3.connect(path)
    db.execute('PRAGMA cache_size=-32768')
    db.execute('PRAGMA temp_store=FILE')
    return db


def segment_records(a,b,pa,pb,way_id,segment_index):
    """The pilot's subdivision identities, plus globally comparable order keys."""
    pa,pb=np.asarray(pa,dtype=float),np.asarray(pb,dtype=float)
    length=float(np.linalg.norm(pb-pa))
    if a==b or length<=0:return [],[]
    count=max(1,math.ceil(length/metric.SPACING));vertices=[];keys=[]
    for j in range(count+1):
        k=f'n{a}' if j==0 else f'n{b}' if j==count else f'e{min(a,b)}:{max(a,b)}:{j if a<b else count-j}'
        point=pa+(pb-pa)*j/count
        vertices.append((k,float(point[0]),float(point[1]),f'{way_id:012}:{segment_index:06}:{j:06}'))
        keys.append(k)
    return vertices,[(*sorted((u,v)),length/count) for u,v in zip(keys,keys[1:])]


def import_identity(root):
    root=Path(root)
    return {'format':1,'sources_sha256':hashlib.sha256((root/'sources.json').read_bytes()).hexdigest(),
            'boundary_sha256':hashlib.sha256((root/'boundary.json').read_bytes()).hexdigest(),
            'poi_config_sha256':hashlib.sha256(Path('poi_config.json').read_bytes()).hexdigest(),
            'metric_version':metric.VERSION,'halo_m':metric.HALO,'spacing_m':metric.SPACING}


def index_sources(root,destination,resume=False):
    root=Path(root);destination=Path(destination)
    identity=import_identity(root);identity_path=destination.with_suffix('.import.json')
    if destination.exists():
        if not resume:raise FileExistsError('Source index already exists; use explicit resume after the old process exits')
        if not identity_path.exists() or json.loads(identity_path.read_text())!=identity:
            raise ValueError('Import checkpoint provenance missing or changed')
    else:
        identity_path.write_text(json.dumps(identity,indent=2),encoding='utf-8')
    # Bound native PBF read-ahead as well as Python's SQLite working set.
    # These are documented libosmium process-local tuning controls.
    runtime={name:os.environ.setdefault(name,'2') for name in
             ['OSMIUM_POOL_THREADS','OSMIUM_MAX_INPUT_QUEUE_SIZE',
              'OSMIUM_MAX_OSMDATA_QUEUE_SIZE','OSMIUM_MAX_WORK_QUEUE_SIZE']}
    started=time.monotonic()
    records=json.loads((root/'sources.json').read_text())
    if len(records)!=6:raise ValueError('All six dated regional extracts are required')
    core_wgs,core=boundary(root/'boundary.json')
    support=core.buffer(metric.HALO+2*metric.SPACING)
    prepare(support)
    coverage=unary_union([transform(TO_METERS.transform,read_poly(root/(r['path'].split('-261001')[0]+'.poly'))) for r in records])
    missing_area=support.difference(coverage).area
    if missing_area>1:
        raise ValueError(f'Source polygons miss {missing_area:.1f} square meters of required context')
    stamps=set()
    for r in records:
        p=root/r['path']
        with p.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=r['sha256']:raise ValueError('Source checksum changed')
        reader=osmium.io.Reader(str(p))
        stamp=reader.header().get('osmosis_replication_timestamp');reader.close()
        stamps.add(stamp)
    if len(stamps)!=1 or not next(iter(stamps)):
        raise ValueError(f'PBF snapshots differ: {sorted(stamps)}')
    db=connect(destination)
    db.executescript('''
      CREATE TABLE IF NOT EXISTS vertices(id INTEGER PRIMARY KEY,k TEXT UNIQUE,x REAL,y REAL,rank TEXT);
      CREATE TABLE IF NOT EXISTS raw_edges(u TEXT,v TEXT,length REAL,PRIMARY KEY(u,v)) WITHOUT ROWID;
      CREATE TABLE IF NOT EXISTS pois(k TEXT PRIMARY KEY,x REAL,y REAL) WITHOUT ROWID;
      CREATE TABLE IF NOT EXISTS ways(id INTEGER PRIMARY KEY,version INTEGER);
      CREATE TABLE IF NOT EXISTS relations(id INTEGER PRIMARY KEY,version INTEGER,members TEXT,poi INTEGER);
      CREATE TABLE IF NOT EXISTS member_bounds(k TEXT PRIMARY KEY,w REAL,s REAL,e REAL,n REAL) WITHOUT ROWID;
      CREATE TABLE IF NOT EXISTS blocked(id INTEGER PRIMARY KEY);
      CREATE TABLE IF NOT EXISTS metadata(k TEXT PRIMARY KEY,value TEXT);
    ''')
    complete=db.execute("SELECT value FROM metadata WHERE k='complete'").fetchone()
    if complete:
        db.close();return json.loads(complete[0])
    config=json.loads(Path('poi_config.json').read_text())
    class Relations(osmium.SimpleHandler):
        def relation(self,r):
            tags=dict(r.tags)
            db.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?,?)',
                       (r.id,r.version,json.dumps([(m.type,m.ref) for m in r.members]),int(bool(allowed_poi(tags,config) and permitted(tags)))))
    h=Relations()
    for r in records:h.apply_file(str(root/r['path']))
    db.commit()
    # Only POI roots and their nested children are needed in memory. Keeping
    # every route/boundary relation inflates 31 MB of JSON into hundreds of MB
    # of Python objects on these six extracts.
    relations={r[0]:(json.loads(r[1]),r[2]) for r in db.execute('SELECT id,members,poi FROM relations WHERE poi=1')}
    pending=list(relations)
    for rid in pending:
        for kind,ref in relations[rid][0]:
            if kind=='r' and ref not in relations:
                row=db.execute('SELECT members,poi FROM relations WHERE id=?',(ref,)).fetchone()
                if row:
                    relations[ref]=(json.loads(row[0]),row[1]);pending.append(ref)
    print(json.dumps({'loaded_poi_relation_graph':len(relations)}),flush=True)
    needed=set();visiting=set()
    def add_members(rid):
        if rid in visiting:return
        visiting.add(rid)
        for kind,ref in relations.get(rid,([],False))[0]:
            if kind=='r':add_members(ref)
            else:needed.add(f'{kind}{ref}')
    for rid,(_,ispoi) in relations.items():
        if ispoi:add_members(rid)
    needed_nodes={int(k[1:]) for k in needed if k.startswith('n')}
    def store_poi(key,xy):
        if xy is not None and support.intersects(Point(*xy)):
            db.execute('INSERT OR IGNORE INTO pois VALUES(?,?,?)',(key,*xy))
    class Features(osmium.SimpleHandler):
        count=0
        seen_ways=0
        def node(self,n):
            if not len(n.tags) and n.id not in needed_nodes:return
            tags=dict(n.tags)
            if ('barrier' in tags or allowed_poi(tags,config)) and not permitted(tags):
                db.execute('INSERT OR IGNORE INTO blocked VALUES(?)',(n.id,))
            key=f'n{n.id}'
            if key in needed:
                db.execute('INSERT OR IGNORE INTO member_bounds VALUES(?,?,?,?,?)',(key,n.location.lon,n.location.lat,n.location.lon,n.location.lat))
            if allowed_poi(tags,config) and permitted(tags):
                store_poi(key,TO_METERS.transform(n.location.lon,n.location.lat))
        def way(self,w):
            self.seen_ways+=1
            if self.seen_ways%100000==0:
                print(json.dumps({'source':self.source_name,'scanned_ways':self.seen_ways,
                                  'location_index_bytes':locations.used_memory(),
                                  'seconds':round(time.monotonic()-started,1)}),flush=True)
            tags=dict(w.tags);key=f'w{w.id}'
            ispoi=allowed_poi(tags,config) and permitted(tags)
            iswalk=walking(tags)
            if not (ispoi or iswalk or key in needed):return
            old=db.execute('SELECT version FROM ways WHERE id=?',(w.id,)).fetchone()
            if old:
                if old[0]!=w.version:raise ValueError('Conflicting OSM versions across source extracts')
                return
            if any(not n.location.valid() for n in w.nodes):
                raise ValueError(f'Incomplete way geometry: {w.id}')
            lon=np.array([n.lon for n in w.nodes]);lat=np.array([n.lat for n in w.nodes])
            if not len(lon):return
            if key in needed:
                db.execute('INSERT OR IGNORE INTO member_bounds VALUES(?,?,?,?,?)',(key,float(lon.min()),float(lat.min()),float(lon.max()),float(lat.max())))
            x,y=TO_METERS.transform(lon,lat);xy=np.column_stack([x,y])
            if not support.intersects(box(float(x.min()),float(y.min()),float(x.max()),float(y.max()))):return
            db.execute('INSERT INTO ways VALUES(?,?)',(w.id,w.version))
            if ispoi:
                store_poi(key,representative({'type':'way','geometry':[{'lon':a,'lat':b} for a,b in zip(lon,lat)]}))
            if not iswalk:return
            refs=[n.ref for n in w.nodes]
            for i,(a,b) in enumerate(zip(refs,refs[1:])):
                if a==b or db.execute('SELECT 1 FROM blocked WHERE id IN (?,?) LIMIT 1',(a,b)).fetchone():continue
                pa,pb=xy[i],xy[i+1];length=float(np.linalg.norm(pb-pa))
                if not length or not support.intersects(LineString([pa,pb])):continue
                vertices,edges=segment_records(a,b,pa,pb,w.id,i)
                db.executemany('''INSERT INTO vertices(k,x,y,rank) VALUES(?,?,?,?)
                  ON CONFLICT(k) DO UPDATE SET x=excluded.x,y=excluded.y,rank=excluded.rank WHERE excluded.rank<vertices.rank''',vertices)
                db.executemany('INSERT INTO raw_edges VALUES(?,?,?) ON CONFLICT(u,v) DO UPDATE SET length=min(length,excluded.length)',
                               edges)
            self.count+=1
            if self.count%10000==0:
                db.commit();print(json.dumps({'indexed_walking_ways':self.count,'seconds':round(time.monotonic()-started,1)}),flush=True)
    handler=Features()
    for r in records:
        checkpoint_key='file:'+r['path']
        if db.execute('SELECT 1 FROM metadata WHERE k=?',(checkpoint_key,)).fetchone():
            print(json.dumps({'reused_source':r['path']}),flush=True);continue
        print(json.dumps({'importing':r['path'],'seconds':round(time.monotonic()-started,1)}),flush=True)
        handler.source_name=r['path']
        # Preserve untagged nodes referenced by POI relations, then use a native
        # tag filter to keep millions of unrelated nodes out of Python callbacks.
        if needed_nodes:
            with osmium.io.Reader(str(root/r['path']),osmium.osm.NODE) as reader:
                osmium.apply(reader,osmium.filter.IdFilter(needed_nodes),handler)
        # Never reopen an interrupted sparse-array index: old entries would be
        # appended to the next stream and could invalidate its sorted lookup.
        cache=destination.parent/f'{destination.stem}.{uuid.uuid4().hex}.locations'
        locations=osmium.index.create_map(f'sparse_file_array,{cache}')
        location_handler=osmium.NodeLocationsForWays(locations)
        node_filter=osmium.filter.KeyFilter('barrier',*config['allow']).enable_for(osmium.osm.NODE)
        with osmium.io.Reader(str(root/r['path'])) as reader:
            osmium.apply(reader,location_handler,node_filter,handler)
        del location_handler
        locations.clear()
        del locations
        gc.collect()
        db.execute('INSERT INTO metadata VALUES(?,?)',(checkpoint_key,r['sha256']))
        db.commit()
        # Only the temporary location index created by this invocation.
        if cache.exists():
            try:cache.unlink()
            except PermissionError:pass  # Windows may retain a mapped-file handle until process exit.
        print(json.dumps({'imported':r['path'],'seconds':round(time.monotonic()-started,1)}),flush=True)
    memo={};unresolved=[]
    def relation_bounds(rid,stack=()):
        if rid in memo:return memo[rid]
        if rid in stack:return None
        parts=[]
        for kind,ref in relations.get(rid,([],False))[0]:
            part=relation_bounds(ref,(*stack,rid)) if kind=='r' else db.execute('SELECT w,s,e,n FROM member_bounds WHERE k=?',(f'{kind}{ref}',)).fetchone()
            if part is None:return None
            parts.append(part)
        if not parts:return None
        arr=np.array(parts);result=(arr[:,0].min(),arr[:,1].min(),arr[:,2].max(),arr[:,3].max());memo[rid]=result
        return result
    for rid,(_,ispoi) in relations.items():
        if ispoi:
            bounds=relation_bounds(rid)
            if bounds is None:unresolved.append(rid);continue
            w,s,e,n=bounds;store_poi(f'r{rid}',TO_METERS.transform((w+e)/2,(s+n)/2))
    # Missing far-away relation members are common in state extracts. They are
    # retained as an explicit release gate instead of silently dropped.
    db.executescript('''
      DROP TABLE IF EXISTS edges;
      DROP TABLE IF EXISTS spatial;
      CREATE TABLE edges AS SELECT a.id AS u,b.id AS v,e.length FROM raw_edges e JOIN vertices a ON a.k=e.u JOIN vertices b ON b.k=e.v;
      CREATE INDEX edges_u ON edges(u); CREATE INDEX edges_v ON edges(v);
      CREATE VIRTUAL TABLE spatial USING rtree(id,x0,x1,y0,y1);
      INSERT INTO spatial SELECT id,x,x,y,y FROM vertices;
      CREATE INDEX IF NOT EXISTS poi_x ON pois(x);
    ''')
    meta={'sources':records,'osm_timestamp':next(iter(stamps)),'boundary_sha256':hashlib.sha256((root/'boundary.json').read_bytes()).hexdigest(),
          'poi_config_sha256':hashlib.sha256(Path('poi_config.json').read_bytes()).hexdigest(),
          'source_coverage_missing_m2':missing_area,'unresolved_relation_ids':unresolved,
          'nodes':db.execute('SELECT count(*) FROM vertices').fetchone()[0],
          'edges':db.execute('SELECT count(*) FROM edges').fetchone()[0],
          'pois':db.execute('SELECT count(*) FROM pois').fetchone()[0],
          'import_runtime':runtime,
          'import_seconds':time.monotonic()-started}
    db.execute('INSERT INTO metadata VALUES(?,?)',('complete',json.dumps(meta)));db.commit();db.close()
    destination.with_suffix('.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    return meta


class SpatialSource:
    def __init__(self,path):
        self.db=connect(path)
        row=self.db.execute("SELECT value FROM metadata WHERE k='complete'").fetchone()
        if not row:raise ValueError('Incomplete source index')
        self.metadata=json.loads(row[0])
        self.db.execute('CREATE TEMP TABLE selected(id INTEGER PRIMARY KEY)')

    def load(self,bounds,max_nodes=150000,max_pois=20000):
        x0,y0,x1,y1=bounds
        rows=self.db.execute('''SELECT v.id,v.x,v.y FROM spatial s JOIN vertices v ON v.id=s.id
          WHERE s.x1>=? AND s.x0<=? AND s.y1>=? AND s.y0<=?
          AND v.x>=? AND v.x<=? AND v.y>=? AND v.y<=? ORDER BY v.rank,v.k LIMIT ?''',
          (x0,x1,y0,y1,x0,x1,y0,y1,max_nodes+1)).fetchall()
        if len(rows)>max_nodes:raise ValueError('Shard graph node budget exceeded')
        ids={r[0]:i for i,r in enumerate(rows)}
        self.db.execute('DELETE FROM selected')
        self.db.executemany('INSERT INTO selected VALUES(?)',[(k,) for k in ids])
        edges=self.db.execute('''SELECT e.u,e.v,e.length FROM selected a CROSS JOIN edges e INDEXED BY edges_u ON e.u=a.id JOIN selected b ON b.id=e.v''').fetchall()
        graph=metric.Graph(np.array([(r[1],r[2]) for r in rows],dtype=float).reshape(-1,2),
                           np.array([(ids[u],ids[v]) for u,v,_ in edges],dtype=np.int64).reshape(-1,2),
                           np.array([d for _,_,d in edges],dtype=float))
        pois=self.db.execute('SELECT x,y FROM pois WHERE x>=? AND x<=? AND y>=? AND y<=? ORDER BY k LIMIT ?',
                             (x0,x1,y0,y1,max_pois+1)).fetchall()
        if len(pois)>max_pois:raise ValueError('Shard POI budget exceeded')
        return graph,np.array(pois,dtype=float).reshape(-1,2)
