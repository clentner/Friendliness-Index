"""Fixed v2 metric in EPSG:32619 meters; no geographic-degree distance math."""
from dataclasses import dataclass
import math
import time
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

VERSION = "boston-front-doors-v2"
RADIUS = 800.0
DECAY = 120.0
SNAP = 75.0
SPACING = 25.0
HALO = RADIUS + 2 * SNAP + SPACING
DISPLAY_MAX = 30.0


@dataclass
class Graph:
    xy: np.ndarray
    edges: np.ndarray
    lengths: np.ndarray

    def subset(self, bounds):
        x0, y0, x1, y1 = bounds
        mask = ((self.xy[:, 0] >= x0) & (self.xy[:, 0] <= x1)
                & (self.xy[:, 1] >= y0) & (self.xy[:, 1] <= y1))
        indices = np.flatnonzero(mask)
        inverse = np.full(len(mask), -1, dtype=np.int64)
        inverse[indices] = np.arange(len(indices))
        keep = mask[self.edges[:, 0]] & mask[self.edges[:, 1]]
        return Graph(self.xy[indices], inverse[self.edges[keep]], self.lengths[keep]), indices

    def matrix(self):
        # Input edges are unique unordered node pairs; duplicate roads must not sum.
        u, v = self.edges.T
        return csr_matrix((np.r_[self.lengths, self.lengths],
                           (np.r_[u, v], np.r_[v, u])),
                          shape=(len(self.xy), len(self.xy)))


def make_graph(nodes, ways, max_segment=SPACING):
    """Preserve OSM identity and adjacent-node geometry, subdividing long edges.

    Parallel ways with identical endpoint IDs use the shortest segment, while
    unrelated OSM nodes at the same coordinate are never merged.
    """
    xy, ids, pairs = [], {}, {}
    def node(key, point):
        if key not in ids:
            ids[key] = len(xy)
            xy.append(point)
        return ids[key]
    for refs in ways:
        for a, b in zip(refs, refs[1:]):
            if a not in nodes or b not in nodes or a == b:
                continue
            pa, pb = np.asarray(nodes[a]), np.asarray(nodes[b])
            length = float(np.linalg.norm(pb - pa))
            if length <= 0:
                continue
            count = max(1, math.ceil(length / max_segment))
            previous = node(a, pa)
            # Stable subdivision identity when a shared OSM edge is reversed.
            for j in range(1, count + 1):
                key = b if j == count else (min(a, b), max(a, b), j if a < b else count-j)
                current = node(key, pa + (pb-pa) * j/count)
                pair = tuple(sorted((previous, current)))
                pairs[pair] = min(pairs.get(pair, math.inf), length/count)
                previous = current
    if not pairs:
        raise ValueError("No usable pedestrian edges in source")
    return Graph(np.asarray(xy, dtype=float), np.asarray(list(pairs), dtype=np.int64),
                 np.asarray(list(pairs.values()), dtype=float))


def snap(xy, points):
    points = np.asarray(points, dtype=float).reshape(-1, 2)
    if not len(xy):
        return np.full(len(points), math.inf), np.zeros(len(points), dtype=np.int64)
    tree = cKDTree(xy)
    distances, indices = tree.query(points,k=2,distance_upper_bound=SNAP+1e-9)
    nearest, nodes = distances[:,0].copy(), indices[:,0].copy()
    # Stable graph-order tie breaking survives spatial subsets (coincident OSM
    # nodes remain topologically distinct and must not switch at chunk edges).
    finite_pairs = np.isfinite(distances).all(axis=1)
    ties = np.flatnonzero(finite_pairs)
    ties = ties[np.abs(distances[ties,1]-nearest[ties])<1e-9]
    for i in ties:
        candidates = tree.query_ball_point(points[i],nearest[i]+1e-9)
        nodes[i] = min(candidates,key=lambda n:(round(float(np.linalg.norm(xy[n]-points[i])),9),n))
        nearest[i] = np.linalg.norm(xy[nodes[i]]-points[i])
    nearest[nearest>SNAP] = math.inf
    return nearest, nodes


def score(graph, queries, pois, deadline=None):
    """Exact sum over POIs, truncated on total connector+network distance.

    Reverse searches grouped by POI snap node. No nearest-only multi-source
    shortcut and no candidate filter in geographic coordinates.
    """
    qdist, qnode = snap(graph.xy, queries)
    pdist, pnode = snap(graph.xy, pois)
    result = np.full(len(queries), np.nan, dtype=np.float64)
    valid = np.isfinite(qdist)
    result[valid] = 0.0
    if not valid.any() or not np.isfinite(pdist).any():
        return result, {"searches": 0, "query_nodes": int(len(set(qnode[valid])))}
    matrix = graph.matrix()
    qidx = np.flatnonzero(valid)
    groups = {}
    for distance, node in zip(pdist, pnode):
        if np.isfinite(distance):
            groups.setdefault(int(node), []).append(distance)
    searches = 0
    for node, offsets in groups.items():
        if deadline and time.monotonic() > deadline:
            raise TimeoutError("Preprocessing time budget exceeded")
        distances = dijkstra(matrix, directed=False, indices=node,
                             limit=RADIUS - min(offsets))[qnode[valid]] + qdist[valid]
        # Sorted offsets + prefix weights preserve multiplicity without a P x N array.
        offsets = np.sort(offsets)
        weights = np.r_[0.0, np.cumsum(np.exp(-offsets / DECAY))]
        count = np.searchsorted(offsets, RADIUS - distances, side="right")
        result[qidx] += np.exp(-distances / DECAY) * weights[count]
        searches += 1
    return result, {"searches": searches, "query_nodes": int(len(set(qnode[valid])))}


def score_chunked(graph, queries, pois, chunk_m=2000.0, deadline=None):
    """Partition query ownership on an absolute projected lattice; discard halos.

    Source graph/POIs must cover the requested region + HALO. Every chunk uses
    the same global graph identity, grid, metric and normalization.
    """
    if chunk_m <= 0:
        raise ValueError("chunk_m must be positive")
    queries, pois = np.asarray(queries), np.asarray(pois).reshape(-1, 2)
    keys = np.floor(queries / chunk_m).astype(np.int64)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    output = np.full(len(queries), np.nan)
    stats = {"chunks": len(unique), "searches": 0, "max_chunk_nodes": 0}
    for i, key in enumerate(unique):
        selected = np.flatnonzero(inverse == i)
        lo = key * chunk_m - HALO
        hi = (key + 1) * chunk_m + HALO
        local, _ = graph.subset((*lo, *hi))
        mask = np.all((pois >= lo) & (pois <= hi), axis=1)
        values, detail = score(local, queries[selected], pois[mask], deadline)
        output[selected] = values
        stats["searches"] += detail["searches"]
        stats["max_chunk_nodes"] = max(stats["max_chunk_nodes"], len(local.xy))
    return output, stats


def display_values(scores):
    return np.clip(np.log1p(scores) / np.log1p(DISPLAY_MAX), 0, 1)
