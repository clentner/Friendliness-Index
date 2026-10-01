"""Bounded, unpublished static pilot build. python -m pilot.build --help"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time
import numpy as np
from pilot import metric
from pilot.source import download, load, projected_bounds
from pilot.tiles import write_tiles


def build(source, bbox, destination, seconds=300, chunk_m=2000):
    started = time.monotonic()
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError("Build destination already exists; choose a new version")
    bounds = projected_bounds(bbox)
    origin = np.floor(bounds[:2]/metric.SPACING)*metric.SPACING
    cols,rows = np.ceil((bounds[2:]-origin)/metric.SPACING).astype(int)
    if rows*cols > 200000:
        raise ValueError("Build limited to 200,000 cells")
    graph,pois,provenance = load(source,bbox)
    extraction = time.monotonic()-started
    x,y = np.meshgrid(origin[0]+(np.arange(cols)+.5)*metric.SPACING,
                      origin[1]+(np.arange(rows)+.5)*metric.SPACING)
    queries = np.column_stack([x.ravel(),y.ravel()])
    scores,stats = metric.score_chunked(graph,queries,pois,chunk_m,started+seconds)
    scoring = time.monotonic()-started-extraction
    scores = scores.reshape(rows,cols).astype("<f4")
    # Write only after scoring has completed successfully. Manifest is written last.
    destination.mkdir(parents=True)
    code_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(Path("pilot").glob("*.py")))).hexdigest()
    config_hash = hashlib.sha256(Path("poi_config.json").read_bytes()).hexdigest()
    score_hash = hashlib.sha256(scores.tobytes()).hexdigest()
    dataset = hashlib.sha256((provenance["sha256"]+metric.VERSION+json.dumps(bbox)+code_hash+config_hash+score_hash).encode()).hexdigest()[:16]
    data_dir = destination/"datasets"/dataset
    data_dir.mkdir(parents=True)
    scores.tofile(data_dir/"scores.f32")
    tile_stats = write_tiles(data_dir/"tiles",scores,origin,bbox)
    for name in ["index.html","app.js","style.css"]:
        shutil.copy2(Path("web")/name,destination/name)
    vendor = Path("web/vendor")
    if not vendor.exists():
        raise FileNotFoundError("Run npm run vendor before building")
    shutil.copytree(vendor,destination/"vendor")
    elapsed = time.monotonic()-started
    metadata = {
        "dataset":dataset,"metric_version":metric.VERSION,"bbox":bbox,
        "generated_at":datetime.now(timezone.utc).isoformat(),"source":provenance,
        "code_sha256":code_hash,"poi_config_sha256":config_hash,"scores_sha256":score_hash,
        "parameters":{"radius_m":metric.RADIUS,"lambda_m":metric.DECAY,
                      "max_snap_m":metric.SNAP,"grid_spacing_m":metric.SPACING,
                      "halo_m":metric.HALO,"display_max":metric.DISPLAY_MAX},
        "grid":{"crs":"EPSG:32619","origin_corner_m":origin.tolist(),
                "shape":[int(rows),int(cols)],"dtype":"little-endian float32",
                "nodata":"NaN","raw_url":f"datasets/{dataset}/scores.f32"},
        "tile_url":f"datasets/{dataset}/tiles/{{z}}/{{x}}/{{y}}.png",**tile_stats,
        "stats":{"nodes":len(graph.xy),"edges":len(graph.edges),"pois":len(pois),
                 "cells":int(scores.size),"reachable":int(np.isfinite(scores).sum()),
                 "max_score":float(np.nanmax(scores)) if np.isfinite(scores).any() else 0,
                 **stats,"extraction_seconds":extraction,"scoring_seconds":scoring,
                 "total_seconds":elapsed,"raw_score_bytes":scores.nbytes}}
    (data_dir/"metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    (destination/"manifest.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["download","build"])
    parser.add_argument("--bbox",required=True,help="west,south,east,north")
    parser.add_argument("--source",default="data/boston.json")
    parser.add_argument("--out",default="build/boston-v2")
    parser.add_argument("--seconds",type=int,default=300)
    args = parser.parse_args()
    bbox = [float(v) for v in args.bbox.split(",")]
    if len(bbox)!=4:
        parser.error("bbox needs four coordinates")
    result = download(bbox,args.source) if args.action=="download" else build(args.source,bbox,args.out,args.seconds)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
