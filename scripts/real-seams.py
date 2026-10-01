"""Check stored Boston grid and chunk seams against unchunked source scoring.

Usage: python scripts/real-seams.py SOURCE MANIFEST.
"""
import json
from pathlib import Path
import sys
import time
import numpy as np

# Support the documented direct-script invocation from the repository root.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pilot.metric import score, score_chunked, SPACING
from pilot.source import load


def main():
    source, manifest_path = sys.argv[1:]
    path=Path(manifest_path)
    manifest=json.loads(path.read_text(encoding="utf-8"))
    graph,pois,_=load(source,manifest["bbox"])
    rows,cols=manifest["grid"]["shape"]
    origin=np.array(manifest["grid"]["origin_corner_m"])
    x,y=np.meshgrid(origin[0]+(np.arange(cols)+.5)*SPACING,
                    origin[1]+(np.arange(rows)+.5)*SPACING)
    all_queries=np.column_stack([x.ravel(),y.ravel()])
    # Sample both sides of every interior 2km chunk seam, plus region edges.
    seam=np.any(np.minimum(all_queries%2000,2000-all_queries%2000)<=40,axis=1)
    boundary=np.zeros((rows,cols),dtype=bool)
    boundary[[0,-1],:]=True;boundary[:,[0,-1]]=True
    rng=np.random.default_rng(20261001)
    selected=[]
    for mask in [seam,boundary.ravel(),np.ones(rows*cols,dtype=bool)]:
        candidates=np.flatnonzero(mask)
        selected.extend(rng.choice(candidates,min(120,len(candidates)),replace=False))
    selected=np.unique(selected)
    queries=all_queries[selected]
    started=time.monotonic()
    reference,_=score(graph,queries,pois,started+120)
    chunked,stats=score_chunked(graph,queries,pois,deadline=started+120)
    stored=np.fromfile(path.parent/manifest["grid"]["raw_url"],dtype="<f4")[selected]
    np.testing.assert_allclose(chunked,reference,rtol=1e-12,atol=1e-12,equal_nan=True)
    np.testing.assert_allclose(stored,reference,rtol=1e-6,atol=1e-6,equal_nan=True)
    result={"dataset":manifest["dataset"],"samples":len(selected),
            "seam_samples":int(seam[selected].sum()),
            "boundary_samples":int(boundary.ravel()[selected].sum()),
            "max_chunk_error":float(np.nanmax(np.abs(chunked-reference))),
            "max_float32_storage_error":float(np.nanmax(np.abs(stored-reference))),
            "seconds":time.monotonic()-started,"chunk_stats":stats,"passed":True}
    output=Path("qa-artifacts");output.mkdir(exist_ok=True)
    (output/"real-seams.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
