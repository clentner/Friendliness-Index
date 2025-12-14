"""Scoring: compute friendliness index for each grid point."""
import numpy as np
import networkx as nx
from typing import Callable
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from scipy.spatial import cKDTree
from config import KernelConfig, KernelType
from indexer import SpatialIndex

# Approximate meters per degree at Boston's latitude
METERS_PER_DEG_LAT = 111000
METERS_PER_DEG_LON = 82000  # cos(42°) * 111000


def exponential_kernel(d: float, lambda_m: float) -> float:
    """Exponential decay kernel: K(d) = exp(-d / lambda_m)"""
    return np.exp(-d / lambda_m)


def power_law_kernel(d: float, p: float, d0_m: float) -> float:
    """Power law kernel: K(d) = 1 / (1 + d/d0_m)^p

    Normalized so K(0) = 1, decays as power law with distance.
    """
    return 1.0 / ((1.0 + d / d0_m) ** p)


def get_kernel_func(config: KernelConfig) -> Callable[[float], float]:
    """Get kernel function based on config."""
    if config.kernel_type == KernelType.EXPONENTIAL:
        return lambda d: exponential_kernel(d, config.lambda_m)
    else:
        return lambda d: power_law_kernel(d, config.p, config.d0_m)


def compute_network_distances(G: nx.Graph, source_node: tuple,
                               target_nodes: set, r_max: float) -> dict:
    """
    Compute network distances from source to targets using truncated Dijkstra.
    Returns dict mapping target_node -> distance.
    """
    if source_node not in G:
        return {}

    try:
        lengths = nx.single_source_dijkstra_path_length(
            G, source_node, cutoff=r_max, weight="weight"
        )
    except nx.NetworkXError:
        return {}

    return {node: dist for node, dist in lengths.items() if node in target_nodes}


_worker_G = None
_worker_snapped_pois = None
_worker_kernel = None
_worker_r_max = None


def _init_worker(G_dict, snapped_pois, kernel_params, r_max):
    """Initialize worker process with shared data."""
    global _worker_G, _worker_snapped_pois, _worker_kernel, _worker_r_max

    _worker_G = nx.Graph()
    for (u, v), w in G_dict.items():
        _worker_G.add_edge(u, v, weight=w)

    _worker_snapped_pois = snapped_pois
    _worker_r_max = r_max

    if kernel_params["type"] == "exponential":
        _worker_kernel = lambda d: exponential_kernel(d, kernel_params["lambda_m"])
    else:
        _worker_kernel = lambda d: power_law_kernel(d, kernel_params["p"], kernel_params["d0_m"])


def _score_single_point(args):
    """Score a single grid point (for multiprocessing)."""
    grid_idx, grid_node, candidate_indices = args

    target_nodes = {tuple(_worker_snapped_pois[i]) for i in candidate_indices}
    distances = compute_network_distances(_worker_G, grid_node, target_nodes, _worker_r_max)
    score = sum(_worker_kernel(d) for d in distances.values())

    return grid_idx, score


def score_grid_points(index: SpatialIndex, kernel_config: KernelConfig,
                      r_max_m: float, parallel: bool = False) -> np.ndarray:
    """
    Compute friendliness scores for all grid points.

    Args:
        index: SpatialIndex containing all spatial data structures
        kernel_config: Kernel configuration
        r_max_m: Maximum influence radius in meters
        parallel: Whether to use multiprocessing

    Returns:
        Array of scores for each grid point
    """
    n_points = len(index.grid_wgs)
    scores = np.zeros(n_points)

    kernel = get_kernel_func(kernel_config)

    graph_nodes = np.array(list(index.G.nodes()))
    graph_tree = cKDTree(graph_nodes)
    _, nearest_indices = graph_tree.query(index.grid_wgs)
    snapped_grid = graph_nodes[nearest_indices]

    if parallel:
        G_dict = {(u, v): d["weight"] for u, v, d in index.G.edges(data=True)}
        kernel_params = {
            "type": kernel_config.kernel_type.value,
            "lambda_m": kernel_config.lambda_m,
            "p": kernel_config.p,
            "d0_m": kernel_config.d0_m,
        }

        tasks = []
        for i in range(n_points):
            candidates = index.get_candidate_pois(i, r_max_m)
            if len(candidates) == 0:
                continue
            tasks.append((i, tuple(snapped_grid[i]), candidates))

        n_workers = multiprocessing.cpu_count()
        with ProcessPoolExecutor(
            max_workers=n_workers,
            initializer=_init_worker,
            initargs=(G_dict, index.snapped_pois, kernel_params, r_max_m)
        ) as executor:
            for grid_idx, score in executor.map(_score_single_point, tasks, chunksize=max(1, len(tasks) // (n_workers * 4))):
                scores[grid_idx] = score
    else:
        for i in range(n_points):
            if i % 500 == 0:
                print(f"  Scoring grid point {i}/{n_points}")

            candidates = index.get_candidate_pois(i, r_max_m)
            if len(candidates) == 0:
                continue

            grid_node = tuple(snapped_grid[i])
            target_nodes = {tuple(index.snapped_pois[j]) for j in candidates}

            distances = compute_network_distances(index.G, grid_node, target_nodes, r_max_m)

            scores[i] = sum(kernel(d) for d in distances.values())

    return scores


def score_grid_points_euclidean(index: SpatialIndex, kernel_config: KernelConfig,
                                 r_max_m: float) -> np.ndarray:
    """
    Compute friendliness scores using Euclidean distance (no graph).

    Much faster than network-based scoring - O(n_grid * log(n_poi)).
    """
    n_points = len(index.grid_wgs)
    scores = np.zeros(n_points)

    kernel = get_kernel_func(kernel_config)

    # Get POI coordinates (original, not snapped to graph)
    poi_coords = np.array([[p.x, p.y] for p in index.pois.geometry])

    # Build k-d tree for POIs (in scaled coordinates for approximate meters)
    poi_scaled = poi_coords * np.array([METERS_PER_DEG_LON, METERS_PER_DEG_LAT])
    poi_tree = cKDTree(poi_scaled)

    # Scale grid points
    grid_scaled = index.grid_wgs * np.array([METERS_PER_DEG_LON, METERS_PER_DEG_LAT])

    # Query all POIs within r_max for each grid point
    for i in range(n_points):
        if i % 500 == 0:
            print(f"  Scoring grid point {i}/{n_points}")

        # Find all POIs within r_max meters
        nearby_indices = poi_tree.query_ball_point(grid_scaled[i], r_max_m)

        if len(nearby_indices) == 0:
            continue

        # Compute distances and sum kernel weights
        nearby_coords = poi_scaled[nearby_indices]
        distances = np.sqrt(np.sum((nearby_coords - grid_scaled[i])**2, axis=1))
        scores[i] = sum(kernel(d) for d in distances)

    return scores


def normalize_scores(scores: np.ndarray, method: str = "log1p") -> np.ndarray:
    """
    Normalize scores for display.

    Args:
        scores: Raw scores
        method: "log1p" or "quantile"

    Returns:
        Normalized scores in [0, 1] range
    """
    if method == "log1p":
        normalized = np.log1p(scores)
    elif method == "quantile":
        from scipy.stats import rankdata
        normalized = rankdata(scores) / len(scores)
    else:
        normalized = scores.copy()

    if normalized.max() > normalized.min():
        normalized = (normalized - normalized.min()) / (normalized.max() - normalized.min())

    return normalized


if __name__ == "__main__":
    from config import BBox, GridConfig, KernelConfig, KernelType
    from extractor import extract_data
    from indexer import create_spatial_index

    test_bbox = BBox.from_string("-71.06,42.358,-71.055,42.362")
    pois, walk_net = extract_data(
        "massachusetts-251213.osm.pbf",
        test_bbox,
        buffer_m=800.0
    )

    grid_config = GridConfig(n_target=500, s_min=15.0, s_max=75.0)
    index = create_spatial_index(pois, walk_net, test_bbox, grid_config)

    kernel_config = KernelConfig(
        kernel_type=KernelType.EXPONENTIAL,
        lambda_m=300.0
    )

    print("\nScoring grid points...")
    scores = score_grid_points(index, kernel_config, r_max_m=800.0, parallel=False)

    print(f"\nScore statistics:")
    print(f"  Min: {scores.min():.4f}")
    print(f"  Max: {scores.max():.4f}")
    print(f"  Mean: {scores.mean():.4f}")
    print(f"  Std: {scores.std():.4f}")
    print(f"  Non-zero: {(scores > 0).sum()}/{len(scores)}")

    normalized = normalize_scores(scores, "log1p")
    print(f"\nNormalized (log1p) range: [{normalized.min():.4f}, {normalized.max():.4f}]")
