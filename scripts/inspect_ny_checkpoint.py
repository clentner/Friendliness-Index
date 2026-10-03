"""Preserve the stopped DB and journal before SQLite's normal crash recovery."""
import hashlib,json,shutil,sqlite3,time
from pathlib import Path
from pilot.regional_source import import_identity

root=Path('data/ny-20261001');backup=Path('qa-artifacts/ny/before-memory-fix')
backup.mkdir(exist_ok=False);started=time.monotonic();files={}
for name in ['source.sqlite','source.sqlite-journal','source.import.json']:
    original=root/name
    if original.exists():
        target=backup/name;shutil.copy2(original,target)
        with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        files[name]={'bytes':target.stat().st_size,'sha256':digest}
        print(json.dumps({'preserved':name,**files[name]}),flush=True)
assert json.loads((root/'source.import.json').read_text())==import_identity(root)
db=sqlite3.connect(root/'source.sqlite');db.execute('PRAGMA cache_size=-32768')
integrity=db.execute('PRAGMA quick_check').fetchall();assert integrity==[('ok',)],integrity
records=json.loads((root/'sources.json').read_text());expected={r['path']:r['sha256'] for r in records}
checkpoints=dict(db.execute("SELECT k,value FROM metadata WHERE k LIKE 'file:%'"))
assert len(checkpoints)==7 and all(value==expected[key[5:]] for key,value in checkpoints.items())
assert 'file:ontario-261001.osm.pbf' not in checkpoints
assert not db.execute("SELECT 1 FROM metadata WHERE k='complete'").fetchone()
db.close()
report={'preserved_files':files,'quick_check':'ok','completed_sources':checkpoints,
        'identity_verified':True,'seconds':time.monotonic()-started}
Path('qa-artifacts/ny/checkpoint-recovery.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
