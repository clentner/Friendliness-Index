"""Guarded parent-source validation chain; stops before the NY graph import."""
import json,shutil,subprocess,sys
from pathlib import Path

def stage(log,seconds,memory,script,*args):
    subprocess.run([sys.executable,'scripts/monitor_stage.py','--log',f'qa-artifacts/ny/{log}.log',
        '--seconds',str(seconds),'--memory-mib',str(memory),sys.executable,script,*args],check=True)

stage('cached-gap-extract-3',300,400,'scripts/extract_ny_gap_parent.py',
    '--parent','data/ny-20261001/new-york-261001.osm.pbf',
    '--out','qa-artifacts/ny/cached-gap-context-3.osm.pbf','--report','qa-artifacts/ny/cached-gap-context-3.json')
stage('cached-gap-audit-3',300,400,'scripts/audit_ny_gap_context.py',
    'qa-artifacts/ny/cached-gap-context-3.osm.pbf','--report','qa-artifacts/ny/cached-gap-audit-3.json')
parent=json.loads(Path('data/ny-parent/parent.json').read_text())
stage('parent-gap-extract',2400,500,'scripts/extract_ny_gap_parent.py',
    '--parent','data/ny-parent/us-261001.osm.pbf','--expected-sha',parent['sha256'],
    '--out','data/ny-20261001/sound-context-261001.osm.pbf','--report','data/ny-20261001/sound-context.derivation.json')
stage('parent-gap-audit',300,400,'scripts/audit_ny_gap_context.py',
    'data/ny-20261001/sound-context-261001.osm.pbf','--report','qa-artifacts/ny/parent-gap-audit.json')
subprocess.run([sys.executable,'scripts/register_ny_parent_context.py'],check=True)
initial=Path('qa-artifacts/ny/source-check-initial.json')
if not initial.exists():shutil.copy2('qa-artifacts/ny/source-check.json',initial)
stage('source-check-parent',300,400,'scripts/ny_source_check.py')
print('Parent source completeness chain passed; graph import remains a separate guarded stage.',flush=True)
