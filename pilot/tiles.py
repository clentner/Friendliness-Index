"""Static Web Mercator raster delivery. Scoring stays on the metric grid."""
import math
from pathlib import Path
import numpy as np
from PIL import Image
from pilot.metric import SPACING, display_values
from pilot.source import TO_METERS

COLORS = np.array([[34,62,92],[52,112,133],[92,166,159],[195,215,161],
                   [250,218,126],[246,156,85],[209,80,61]],dtype=float)


def tile_coordinate(lon, lat, zoom):
    scale = 2**zoom
    return ((lon+180)/360*scale,
            (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*scale)


def sample_grid(scores, origin, lon, lat):
    x,y = TO_METERS.transform(lon,lat)
    # Grid locations are cell centers on an absolute EPSG:32619 lattice.
    col = np.floor((x-origin[0])/SPACING).astype(int)
    row = np.floor((y-origin[1])/SPACING).astype(int)
    valid = (row>=0)&(row<scores.shape[0])&(col>=0)&(col<scores.shape[1])
    values = np.full(np.shape(lon),np.nan)
    values[valid] = scores[row[valid],col[valid]]
    return values


def colorize(values):
    finite = np.isfinite(values)
    normalized = display_values(np.where(finite,values,0))
    t = normalized*(len(COLORS)-1)
    low = np.floor(t).astype(int)
    high = np.minimum(low+1,len(COLORS)-1)
    colors = COLORS[low]*(1-(t-low))[...,None] + COLORS[high]*(t-low)[...,None]
    # Unreachable/uncomputed transparent, reachable zero remains visible blue.
    return np.dstack([colors.astype(np.uint8),np.where(finite,210,0).astype(np.uint8)])


def write_tiles(directory, scores, origin, bbox, minzoom=9, maxzoom=14):
    directory = Path(directory)
    west,south,east,north = bbox
    x0,y0 = tile_coordinate(west,north,maxzoom)
    x1,y1 = tile_coordinate(east,south,maxzoom)
    if (math.floor(x1)-math.floor(x0)+1)*(math.floor(y1)-math.floor(y0)+1) > 400:
        raise ValueError("Tile budget exceeded")
    current = set()
    count = 0
    for tx in range(math.floor(x0),math.floor(x1)+1):
        for ty in range(math.floor(y0),math.floor(y1)+1):
            px,py = np.meshgrid(np.arange(256)+.5,np.arange(256)+.5)
            lon = (tx+px/256)/2**maxzoom*360-180
            lat = np.degrees(np.arctan(np.sinh(math.pi*(1-2*(ty+py/256)/2**maxzoom))))
            values = sample_grid(scores,origin,lon,lat)
            # Exact requested WGS84 coverage; expanded UTM rectangle is internal.
            values[(lon<west)|(lon>east)|(lat<south)|(lat>north)] = np.nan
            target = directory/str(maxzoom)/str(tx)/f"{ty}.png"
            target.parent.mkdir(parents=True,exist_ok=True)
            Image.fromarray(colorize(values)).save(target,optimize=True)
            current.add((tx,ty))
            count += 1
    for z in range(maxzoom-1,minzoom-1,-1):
        parents = {(x//2,y//2) for x,y in current}
        for tx,ty in parents:
            canvas = Image.new("RGBA",(512,512))
            for dx in range(2):
                for dy in range(2):
                    child = directory/str(z+1)/str(tx*2+dx)/f"{ty*2+dy}.png"
                    if child.exists():
                        with Image.open(child) as image:
                            canvas.paste(image,(dx*256,dy*256))
            target = directory/str(z)/str(tx)/f"{ty}.png"
            target.parent.mkdir(parents=True,exist_ok=True)
            canvas.resize((256,256),Image.Resampling.LANCZOS).save(target,optimize=True)
            count += 1
        current = parents
    return {"tiles":count,"bytes":sum(p.stat().st_size for p in directory.rglob("*.png")),
            "minzoom":minzoom,"maxzoom":maxzoom,"tile_size":256}
