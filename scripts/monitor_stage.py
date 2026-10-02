"""Run one worker with a working-set, system headroom and wall-clock budget."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import time

class Memory(ctypes.Structure):
    _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(n,ctypes.c_ulonglong) for n in ['total_phys','available_phys','total_page','available_page','total_virtual','available_virtual','extended']]

class Counters(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ['peak','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile']]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--log',required=True)
    parser.add_argument('--seconds',type=int,default=1800)
    parser.add_argument('--memory-mib',type=int,default=1100)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();log=Path(args.log);log.parent.mkdir(parents=True,exist_ok=True)
    get_memory=ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    get_memory.restype=wintypes.BOOL
    started=time.monotonic();peak=0;minimum_available=2**64;reason=None
    with log.open('w',encoding='utf-8') as output:
        child=subprocess.Popen(args.command,stdout=output,stderr=subprocess.STDOUT)
        while child.poll() is None:
            memory=Memory();memory.length=ctypes.sizeof(memory)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
            counters=Counters();counters.cb=ctypes.sizeof(counters)
            if get_memory(int(child._handle),ctypes.byref(counters),ctypes.sizeof(counters)):peak=max(peak,counters.peak)
            minimum_available=min(minimum_available,memory.available_phys)
            if time.monotonic()-started>args.seconds:reason='Wall-clock budget exceeded'
            if peak>args.memory_mib*1024**2:reason='Working-set budget exceeded'
            if memory.available_phys<384*1024**2:reason='System available RAM below 384 MiB'
            status={'pid':child.pid,'seconds':round(time.monotonic()-started,2),'peak_working_set_bytes':peak,
                    'minimum_available_ram_bytes':minimum_available,'stopped_reason':reason}
            log.with_suffix('.resources.json').write_text(json.dumps(status,indent=2))
            if reason:child.terminate();child.wait(timeout=10);break
            time.sleep(1)
    status['exit_code']=child.returncode
    log.with_suffix('.resources.json').write_text(json.dumps(status,indent=2))
    print(json.dumps(status));return child.returncode or (1 if reason else 0)

if __name__=='__main__':sys.exit(main())
