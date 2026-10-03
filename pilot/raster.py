"""Bounded mappings for rasters larger than the process working-set budget."""
from pathlib import Path
import numpy as np


class DiskRaster:
    def __init__(self, path, shape, create=False):
        self.path=Path(path);self.shape=tuple(shape);self.size=int(np.prod(shape))
        if create:
            temporary=self.path.with_suffix('.initializing')
            block=np.full((min(64,shape[0]),shape[1]),np.nan,dtype='<f4')
            with temporary.open('wb') as stream:
                for row in range(0,shape[0],64):
                    block[:min(64,shape[0]-row)].tofile(stream)
            temporary.replace(self.path)
        if self.path.stat().st_size != self.size*4:
            raise ValueError('Raster size mismatch')

    def access(self, key, value=None):
        row,col=key
        if isinstance(row,slice):
            start,stop,step=row.indices(self.shape[0])
            local=slice(0,stop-start,step)
        else:
            if np.size(row)==0:return np.array([],dtype='<f4')
            start,stop=int(np.min(row)),int(np.max(row))+1
            local=np.asarray(row)-start
        if stop<=start:return np.empty((0,0),dtype='<f4')
        mapped=np.memmap(self.path,mode='r+' if value is not None else 'r',
            offset=start*self.shape[1]*4,shape=(stop-start,self.shape[1]),dtype='<f4')
        try:
            if value is None:return np.array(mapped[local,col],copy=True)
            mapped[local,col]=value;mapped.flush()
        finally:
            mapped._mmap.close()

    def __getitem__(self,key):return self.access(key)
    def __setitem__(self,key,value):self.access(key,value)
    def flush(self):pass
