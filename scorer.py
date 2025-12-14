"""Scoring: compute friendliness index for each grid point."""
import numpy as np
import networkx as nx
from typing import Callable
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from config import KernelConfig, KernelType
from indexer import SpatialIndex


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


def score_single_grid_point(args):
    """Score a single grid point (for multiprocessing)."""
    grid_idx, grid_node, G_dict, poi_nodes, candidate_indices, snapped_pois, r_max, kernel_params = args

    G = nx.Graph()
    for (u, v), w in G_dict.items():
        G.add_edge(u, v, weight=w)

    if kernel_params["type"] == "exponential":
        kernel = lambda d: exponential_kernel(d, kernel_params["lambda_m"])
    else:
        kernel = lambda d: power_law_kernel(d, kernel_params["p"], kernel_params["d0_m"])

    target_nodes = {tuple(snapped_pois[i]) for i in candidate_indices}

    distances = compute_network_distances(G, grid_node, target_nodes, r_max)

    score = sum(kernel(d) for d in distances.values())
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

    snapped_grid = np.array([
        min(index.G.nodes(), key=lambda n: (n[0] - pt[0])**2 + (n[1] - pt[1])**2)
        for pt in index.grid_wgs
    ])

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
            tasks.append((
                i, tuple(snapped_grid[i]), G_dict, index.snapped_poi_set,
                candidates, index.snapped_pois, r_max_m, kernel_params
            ))

        with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
            for grid_idx, score in executor.map(score_single_grid_point, tasks):
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
