"""Continue the authorized local NY build when guarded RAM headroom is available.

No publication or service/account changes. One worker lock prevents duplicates.
Every failed data/test gate stops the chain; resource retries preserve checkpoints.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from monitor_stage import Memory,atomic_status

ROOT=Path('qa-artifacts/ny');LOCK=ROOT/'worker.lock';STATUS=ROOT/'worker-status.json'


def headroom():
    memory=Memory();memory.length=ctypes.sizeof(memory)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
    return memory.available_phys


def ready(name,mib,timeout=3600):
    started=time.monotonic();stable=0
    while True:
        available=headroom();stable=stable+1 if available>=mib*1024**2 else 0
        atomic_status(STATUS,{'pid':os.getpid(),'stage':name,'state':'waiting_for_ram',
            'available_ram_bytes':available,'required_ram_bytes':mib*1024**2,
            'wait_seconds':round(time.monotonic()-started,1)})
        if stable>=3:return
        if time.monotonic()-started>timeout:raise RuntimeError('RAM headroom did not recover within one hour')
        time.sleep(5)


def stage(name,seconds,memory,script,*args):
    previous=[int(p.stem.rsplit('-',1)[1]) for p in ROOT.glob(f'{name}-*.log')
              if p.stem.rsplit('-',1)[1].isdigit()]
    first=max(previous,default=0)+1
    for attempt in range(first,first+3):
        ready(name,memory+512)
        log=ROOT/f'{name}-{attempt}.log'
        if log.exists():raise FileExistsError(f'Inspect existing stage before rerun: {log}')
        attempt_args=list(args)
        if name=='ny-export' and Path('build/new-york').exists() and '--resume-export' not in attempt_args:
            attempt_args.append('--resume-export')
        atomic_status(STATUS,{'pid':os.getpid(),'stage':name,'state':'running','attempt':attempt,'log':str(log)})
        result=subprocess.run([sys.executable,'scripts/monitor_stage.py','--log',str(log),
            '--seconds',str(seconds),'--memory-mib',str(memory),sys.executable,script,*attempt_args])
        if result.returncode==0:return
        resources=json.loads(log.with_suffix('.resources.json').read_text())
        if resources.get('stopped_reason')!='System available RAM below 384 MiB':
            raise RuntimeError(f'{name} failed; inspect {log}')
    raise RuntimeError(f'{name} stopped for low system RAM three times; checkpoints retained')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume-import',action='store_true',
        help='Resume the existing verified import without re-registering immutable sources')
    options=parser.parse_args()
    ROOT.mkdir(exist_ok=True)
    with LOCK.open('x') as stream:json.dump({'pid':os.getpid(),'command':'scripts/continue_ny_build.py'},stream)
    try:
        stage('final-tests',300,400,'-m','unittest','discover','-s','tests','-v')
        if options.resume_import:
            if not Path('data/ny-20261001/source.sqlite').is_file():
                raise FileNotFoundError('No existing source database to resume')
        else:
            parent=json.loads(Path('data/ny-parent/parent.json').read_text())
            context=Path('data/ny-20261001/sound-context-261001.osm.pbf')
            if not context.exists():
                stage('parent-context-resume',2400,500,'scripts/extract_ny_gap_parent.py',
                    '--parent',parent['path'],'--expected-sha',parent['sha256'],'--out',str(context),
                    '--report','data/ny-20261001/sound-context.derivation.json')
            stage('parent-context-audit',300,400,'scripts/audit_ny_gap_context.py',str(context),
                '--report','qa-artifacts/ny/parent-gap-audit.json')
            stage('parent-context-register',300,300,'scripts/register_ny_parent_context.py')
            initial=ROOT/'source-check-initial.json'
            if not initial.exists():shutil.copy2(ROOT/'source-check.json',initial)
            stage('complete-source-check',300,400,'scripts/ny_source_check.py')
        # Explicit resume is safe here: this single worker owns and waits for
        # each child, and every importer verifies immutable source identity.
        stage('ny-import',14400,1100,'-c',
            "from pathlib import Path;from pilot.regional_source import index_sources;p=Path('data/ny-20261001/source.sqlite');index_sources(p.parent,p,resume=p.exists())")
        metadata=json.loads(Path('data/ny-20261001/source.json').read_text())
        if metadata['unresolved_relation_ids']:raise RuntimeError('Unresolved source relations require inspection before scoring')
        common=['--source-root','data/ny-20261001','--index','data/ny-20261001/source.sqlite','--run','build/ny-run']
        stage('ny-samples',1200,500,'-m','pilot.region','score',*common,'--sample')
        stage('ny-access-audit',1200,400,'scripts/audit-region-access.py','--root','data/ny-20261001',
            '--run','build/ny-run','--report','qa-artifacts/ny/access-audit.json')
        stage('ny-seams',1800,700,'scripts/ny-seams.py')
        stage('ny-scoring',14400,500,'-m','pilot.region','score',*common)
        stage('ny-scoring-summary',300,300,'scripts/report-region-scoring.py','--run','build/ny-run',
            '--report','qa-artifacts/ny/scoring-summary.json')
        stage('ny-export',14400,700,'-m','pilot.region','export',*common,'--out','build/new-york',
            '--archive-staging',*(['--resume-export'] if Path('build/new-york').exists() else []))
        stage('ny-export-verification',1800,500,'scripts/verify-region.py','--site','build/new-york',
            '--run','build/ny-run','--source','data/ny-20261001/source.sqlite',
            '--audit','qa-artifacts/ny/access-audit.json','--report','qa-artifacts/ny/verification.json','--archive-staging')
        atomic_status(STATUS,{'pid':os.getpid(),'state':'local_export_verified',
            'next':'Measure archive packaging, browser transfers and exact incremental hosting impact. Publication requires approval.'})
    except Exception as error:
        atomic_status(STATUS,{'pid':os.getpid(),'state':'stopped','error':str(error)})
        raise
    finally:
        if json.loads(LOCK.read_text())['pid']==os.getpid():LOCK.unlink()


if __name__=='__main__':main()
