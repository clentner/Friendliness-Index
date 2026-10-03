"""Prove remote relation completeness, then repair metadata without graph writes."""
import os
for key in ['OSMIUM_POOL_THREADS','OSMIUM_MAX_INPUT_QUEUE_SIZE','OSMIUM_MAX_OSMDATA_QUEUE_SIZE','OSMIUM_MAX_WORK_QUEUE_SIZE']:os.environ.setdefault(key,'2')
import argparse,json,shutil,sqlite3,time
from pathlib import Path
from pilot import metric
from pilot.regional_source import boundary,connect,import_identity
from scripts.pbf_block_index import build,sha,atomic
from scripts.relation_context import extract,audit


def protect_graph(action,table,column,database,trigger):
    if action in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE):
        return sqlite3.SQLITE_OK if table in ('member_bounds','metadata') else sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_CREATE_INDEX,sqlite3.SQLITE_CREATE_TABLE,sqlite3.SQLITE_CREATE_TRIGGER,
                  sqlite3.SQLITE_CREATE_VIEW,sqlite3.SQLITE_DROP_INDEX,sqlite3.SQLITE_DROP_TABLE,
                  sqlite3.SQLITE_DROP_TRIGGER,sqlite3.SQLITE_DROP_VIEW,sqlite3.SQLITE_ALTER_TABLE):return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    started=time.monotonic();root=Path('data/ny-20261001');database=root/'source.sqlite'
    if Path('qa-artifacts/ny/worker.lock').exists():raise RuntimeError('Build worker lock exists; do not edit a live graph')
    db=connect(database);original=db.execute("SELECT value FROM metadata WHERE k='complete'").fetchone()[0]
    metadata=json.loads(original);identity=import_identity(root)
    if json.loads((root/'source.import.json').read_text())!=identity:raise ValueError('Import identity changed')
    if metadata.get('relation_completion'):
        from pilot.regional_source import validate_relation_completion
        validate_relation_completion(root,metadata)
        if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('Repaired database integrity check failed')
        atomic(root/'source.json',metadata)
        db.close();print('Verified already-applied relation repair');return
    roots=metadata['unresolved_relation_ids']
    if set(roots)!={4233353,13058969}:raise ValueError('Unexpected unresolved relations; inspect before repair')
    expected={};pending=list(roots)
    for rid in pending:
        row=db.execute('SELECT version,members FROM relations WHERE id=?',(rid,)).fetchone()
        if not row:raise ValueError('Missing imported relation record')
        expected[rid]=(row[0],json.loads(row[1]))
        for kind,ref in expected[rid][1]:
            if kind=='r' and ref not in pending:pending.append(ref)
    keys={f'{kind}{ref}' for _,members in expected.values() for kind,ref in members if kind!='r'}
    known={}
    for key in keys:
        row=db.execute('SELECT w,s,e,n FROM member_bounds WHERE k=?',(key,)).fetchone()
        if row:known[key]=row
    checkpoints=dict(db.execute("SELECT k,value FROM metadata WHERE k LIKE 'file:%'"))
    wanted={'file:'+r['path']:r['sha256'] for r in metadata['sources']}
    if checkpoints!=wanted or len(checkpoints)!=10:raise ValueError('Completed source checkpoints differ')
    db.close()
    parent=json.loads(Path('data/ny-parent/parent.json').read_text())
    index=build(parent['path'],'data/ny-parent/us-261001.block-index.json',parent['sha256'])
    context=root/'relation-completion-261001.osm.pbf';report_path=root/'relation-completion.json'
    if not context.exists():extract(parent['path'],index['index'],roots,context)
    elif not report_path.exists():raise ValueError('Unregistered relation extract requires inspection')
    _,core=boundary(root/'boundary.json');support=core.buffer(metric.HALO+2*metric.SPACING)
    result,bounds=audit(context,roots,expected,support,json.loads(Path('poi_config.json').read_text()),known)
    if result['timestamp']!=metadata['osm_timestamp']:raise ValueError('Relation context snapshot differs')
    added=sorted(keys-set(known))
    proof={'format':1,'import_identity':identity,'unresolved_before':roots,'source_checkpoints':checkpoints,
           'audit_code_sha256':sha(Path(__file__).with_name('relation_context.py')),'repair_code_sha256':sha(__file__),
           'parent_sha256':parent['sha256'],'parent_bytes':parent['bytes'],
           'block_index_sha256':sha('data/ny-parent/us-261001.block-index.json'),
           'extract':context.name,'extract_sha256':sha(context),'extract_bytes':context.stat().st_size,
           'added_member_keys':added,'known_member_bounds_exact':len(known),**result}
    if report_path.exists() and json.loads(report_path.read_text())!=proof:raise ValueError('Relation proof changed')
    atomic(report_path,proof)
    print(json.dumps({'proof':str(report_path),'roots':result['roots'],'counts':result['counts'],'added_bounds':len(added)}),flush=True)
    if not args.apply:return
    backup=Path('qa-artifacts/ny/before-relation-repair');backup.mkdir(exist_ok=True)
    manifest=backup/'backup.json'
    if not manifest.exists():
        files={}
        for name in ['source.sqlite','source.json','source.import.json']:
            target=backup/name
            if target.exists():raise ValueError('Incomplete repair backup requires inspection')
            shutil.copy2(root/name,target);files[name]={'bytes':target.stat().st_size,'sha256':sha(target)}
        atomic(manifest,{'files':files,'checkpoints':checkpoints})
    else:
        saved=json.loads(manifest.read_text())
        if saved['checkpoints']!=checkpoints or saved['files']['source.sqlite']['sha256']!=sha(database):
            raise ValueError('Existing backup is not this unrepaired database')
    db=connect(database)
    if db.execute("SELECT value FROM metadata WHERE k='complete'").fetchone()[0]!=original:raise ValueError('Import metadata changed during proof')
    db.set_authorizer(protect_graph)
    metadata['unresolved_relation_ids']=[]
    metadata['relation_completion']={'report':report_path.name,'sha256':sha(report_path),'resolved_relations':roots,
                                     'graph_and_poi_tables_unchanged':True}
    with db:
        db.executemany('INSERT INTO member_bounds VALUES(?,?,?,?,?)',[(key,*bounds[key]) for key in added])
        db.execute("UPDATE metadata SET value=? WHERE k='complete'",(json.dumps(metadata),))
        if dict(db.execute("SELECT k,value FROM metadata WHERE k LIKE 'file:%'"))!=checkpoints:raise ValueError('Source checkpoints changed')
    db.set_authorizer(None)
    if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('Repaired database integrity check failed')
    db.close();atomic(root/'source.json',metadata)
    atomic(Path('qa-artifacts/ny/relation-repair.json'),{'proof':str(report_path),'proof_sha256':sha(report_path),
           'backup':str(backup),'quick_check':'ok','source_checkpoints_preserved':len(checkpoints),
           'graph_and_poi_tables_unchanged':True,'added_member_bounds':len(added),'seconds':time.monotonic()-started})
    print(json.dumps({'applied':True,'seconds':time.monotonic()-started}),flush=True)


if __name__=='__main__':main()
