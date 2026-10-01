"""Small reproducible synthetic performance + chunk-equivalence benchmark."""
import json
import time
import numpy as np
from pilot.metric import make_graph,score,score_chunked

nodes={r*25+c:(c*50.,r*50.) for r in range(25) for c in range(25)}
ways=[]
for r in range(25):
    ways.append([r*25+c for c in range(25)])
for c in range(25):
    ways.append([r*25+c for r in range(25)])
graph=make_graph(nodes,ways)
rng=np.random.default_rng(20261001)
pois=rng.uniform(0,1200,(150,2))
queries=rng.uniform(0,1200,(2500,2))
start=time.perf_counter()
expected,stats=score(graph,queries,pois)
reference=time.perf_counter()-start
start=time.perf_counter()
actual,chunks=score_chunked(graph,queries,pois,500)
elapsed=time.perf_counter()-start
np.testing.assert_allclose(actual,expected,rtol=1e-12,atol=1e-12)
print(json.dumps({'fixture':'synthetic connected 1.2km lattice','nodes':len(graph.xy),
 'pois':len(pois),'queries':len(queries),'reference_seconds':reference,
 'chunked_seconds':elapsed,'max_absolute_error':float(np.max(np.abs(actual-expected))),
 'reference_stats':stats,'chunk_stats':chunks},indent=2))
