"""Read-only Windows resident/committed memory attribution for our own worker."""
import ctypes as c
from ctypes import wintypes as w
from collections import defaultdict
from scripts.monitor_stage import Counters


class Region(c.Structure):
    _fields_=[('base',c.c_void_p),('allocation',c.c_void_p),('allocation_protect',w.DWORD),
              ('partition',w.WORD),('size',c.c_size_t),('state',w.DWORD),('protect',w.DWORD),('kind',w.DWORD)]


class Page(c.Structure):
    _fields_=[('address',c.c_void_p),('flags',c.c_size_t)]


def snapshot():
    kernel=c.WinDLL('kernel32',use_last_error=True);psapi=c.WinDLL('psapi',use_last_error=True)
    kernel.GetCurrentProcess.restype=w.HANDLE;handle=kernel.GetCurrentProcess()
    kernel.VirtualQuery.argtypes=[c.c_void_p,c.POINTER(Region),c.c_size_t];kernel.VirtualQuery.restype=c.c_size_t
    psapi.QueryWorkingSetEx.argtypes=[w.HANDLE,c.c_void_p,w.DWORD];psapi.QueryWorkingSetEx.restype=w.BOOL
    psapi.GetMappedFileNameW.argtypes=[w.HANDLE,c.c_void_p,w.LPWSTR,w.DWORD]
    psapi.GetProcessMemoryInfo.argtypes=[w.HANDLE,c.POINTER(Counters),w.DWORD]
    counters=Counters();counters.cb=c.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(handle,c.byref(counters),c.sizeof(counters)):raise c.WinError(c.get_last_error())
    totals=defaultdict(lambda:{'committed':0,'resident':0});locations=[];address=0
    while True:
        region=Region()
        if not kernel.VirtualQuery(address,c.byref(region),c.sizeof(region)):break
        base=region.base or 0;end=base+region.size
        if end<=address:break
        address=end
        if region.state!=0x1000:continue
        kind={0x20000:'private',0x40000:'mapped',0x1000000:'image'}.get(region.kind,str(region.kind))
        resident=0
        for begin in range(base,end,4096*4096):
            count=min(4096,(end-begin+4095)//4096);pages=(Page*count)()
            for i in range(count):pages[i].address=begin+i*4096
            if not psapi.QueryWorkingSetEx(handle,pages,c.sizeof(pages)):raise c.WinError(c.get_last_error())
            resident+=sum(bool(page.flags&1) for page in pages)*4096
        totals[kind]['committed']+=region.size;totals[kind]['resident']+=resident
        if region.kind==0x40000:
            name=c.create_unicode_buffer(32768)
            if psapi.GetMappedFileNameW(handle,base,name,len(name)) and name.value.endswith(('.locations','.nodes.bin')):
                locations.append({'path':name.value,'mapped_bytes':region.size,'resident_bytes':resident})
    return {'working_set_bytes':counters.working,'peak_working_set_bytes':counters.peak,
            'private_commit_bytes':counters.pagefile,'peak_private_commit_bytes':counters.peak_pagefile,
            'page_faults':counters.faults,'regions':dict(totals),'location_maps':locations}
