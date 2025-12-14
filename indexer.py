"""Indexing: graph construction, POI snapping, and grid generation."""
import numpy as np
import networkx as nx
import geopandas as gpd
from scipy.spatial import cKDTree
from shapely.geometry import Point
from pyproj import Transformer
from config import BBox, GridConfig


def get_utm_zone(lon: float, lat: float) -> str:
    """Get UTM zone EPSG code for a given lon/lat."""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return f"EPSG:326{zone:02d}"
    return f"EPSG:327{zone:02d}"


def build_walk_graph(walk_net: gpd.GeoDataFrame) -> nx.Graph:
    """
    Build a networkx graph from the walk network edges.
    Edge weights are distances in meters.
    Returns only the largest connected component.
    """
    from shapely.geometry import LineString, MultiLineString

    G = nx.Graph()

    def add_linestring(geom, length_hint=None):
        coords = list(geom.coords)
        if len(coords) < 2:
            return
        start = coords[0]
        end = coords[-1]
        if length_hint is not None and not np.isnan(length_hint):
            length = length_hint
        else:
            length = geom.length * 111320
        G.add_edge(start, end, weight=length)

    for idx, row in walk_net.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        length = row.get("length")

        if isinstance(geom, MultiLineString):
            for line in geom.geoms:
                add_linestring(line)
        elif isinstance(geom, LineString):
            add_linestring(geom, length)

    print(f"Raw graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Keep only the largest connected component
    components = list(nx.connected_components(G))
    if len(components) > 1:
        main_component = max(components, key=len)
        G = G.subgraph(main_component).copy()
        print(f"Filtered to main component: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        print(f"  (removed {len(components) - 1} disconnected components)")

    return G


def snap_points_to_graph(points: gpd.GeoDataFrame, G: nx.Graph) -> np.ndarray:
    """
    Snap points to nearest graph node.
    Returns array of node tuples (lon, lat).
    """
    nodes = np.array(list(G.nodes()))
    tree = cKDTree(nodes)

    point_coords = np.array([[p.x, p.y] for p in points.geometry])
    _, indices = tree.query(point_coords)

    return nodes[indices]


def generate_grid(bbox: BBox, grid_config: GridConfig) -> tuple[np.ndarray, float]:
    """
    Generate a grid of points inside the bounding box.

    Returns:
        Tuple of (grid_points_wgs84, spacing_m)
        grid_points_wgs84: (N, 2) array of (lon, lat) points
    """
    center_lat = (bbox.min_lat + bbox.max_lat) / 2
    center_lon = (bbox.min_lon + bbox.max_lon) / 2
    utm_crs = get_utm_zone(center_lon, center_lat)

    to_utm = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    to_wgs = Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True)

    min_x, min_y = to_utm.transform(bbox.min_lon, bbox.min_lat)
    max_x, max_y = to_utm.transform(bbox.max_lon, bbox.max_lat)

    area_m2 = (max_x - min_x) * (max_y - min_y)
    spacing = np.sqrt(area_m2 / grid_config.n_target)
    spacing = np.clip(spacing, grid_config.s_min, grid_config.s_max)

    xs = np.arange(min_x, max_x, spacing)
    ys = np.arange(min_y, max_y, spacing)
    grid_utm = np.array([(x, y) for y in ys for x in xs])

    grid_wgs = np.array([to_wgs.transform(x, y) for x, y in grid_utm])

    print(f"Generated {len(grid_wgs)} grid points with {spacing:.1f}m spacing")
    return grid_wgs, spacing


def build_poi_kdtree(snapped_pois: np.ndarray, bbox: BBox) -> tuple[cKDTree, np.ndarray]:
    """
    Build a k-d tree for POI prefiltering in metric coordinates.

    Returns:
        Tuple of (kdtree, poi_coords_m) where poi_coords_m is in meters
    """
    center_lat = (bbox.min_lat + bbox.max_lat) / 2
    center_lon = (bbox.min_lon + bbox.max_lon) / 2
    utm_crs = get_utm_zone(center_lon, center_lat)

    to_utm = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)

    poi_coords_m = np.array([to_utm.transform(lon, lat) for lon, lat in snapped_pois])

    tree = cKDTree(poi_coords_m)
    return tree, poi_coords_m


class SpatialIndex:
    """Container for all spatial indices needed for scoring."""

    def __init__(self, G: nx.Graph, pois: gpd.GeoDataFrame, snapped_pois: np.ndarray,
                 grid_wgs: np.ndarray, grid_spacing: float, bbox: BBox):
        self.G = G
        self.pois = pois
        self.snapped_pois = snapped_pois
        self.grid_wgs = grid_wgs
        self.grid_spacing = grid_spacing
        self.bbox = bbox

        center_lat = (bbox.min_lat + bbox.max_lat) / 2
        center_lon = (bbox.min_lon + bbox.max_lon) / 2
        self.utm_crs = get_utm_zone(center_lon, center_lat)
        self.to_utm = Transformer.from_crs("EPSG:4326", self.utm_crs, always_xy=True)

        self.poi_kdtree, self.poi_coords_m = build_poi_kdtree(snapped_pois, bbox)

        self.snapped_poi_set = set(map(tuple, snapped_pois))

        self.grid_coords_m = np.array([self.to_utm.transform(lon, lat) for lon, lat in grid_wgs])

    def get_candidate_pois(self, grid_idx: int, r_max_m: float) -> np.ndarray:
        """Get indices of POIs within straight-line distance of grid point."""
        grid_pt_m = self.grid_coords_m[grid_idx]
        indices = self.poi_kdtree.query_ball_point(grid_pt_m, r_max_m)
        return np.array(indices)


def create_spatial_index(pois: gpd.GeoDataFrame, walk_net: gpd.GeoDataFrame,
                         bbox: BBox, grid_config: GridConfig) -> SpatialIndex:
    """Create all spatial indices for scoring."""
    print("Building walk graph...")
    G = build_walk_graph(walk_net)

    print("Snapping POIs to graph...")
    snapped_pois = snap_points_to_graph(pois, G)
    print(f"Snapped {len(snapped_pois)} POIs")

    print("Generating grid...")
    grid_wgs, spacing = generate_grid(bbox, grid_config)

    return SpatialIndex(G, pois, snapped_pois, grid_wgs, spacing, bbox)


if __name__ == "__main__":
    from config import GridConfig
    from extractor import extract_data

    test_bbox = BBox.from_string("-71.065,42.355,-71.055,42.362")
    pois, walk_net = extract_data(
        "massachusetts-251213.osm.pbf",
        test_bbox,
        buffer_m=500.0
    )

    grid_config = GridConfig(n_target=5000, s_min=15.0, s_max=75.0)
    index = create_spatial_index(pois, walk_net, test_bbox, grid_config)

    print(f"\nSpatial index created:")
    print(f"  Graph: {index.G.number_of_nodes()} nodes, {index.G.number_of_edges()} edges")
    print(f"  POIs: {len(index.snapped_pois)}")
    print(f"  Grid: {len(index.grid_wgs)} points at {index.grid_spacing:.1f}m spacing")

    candidates = index.get_candidate_pois(0, 500.0)
    print(f"  Sample: {len(candidates)} POI candidates within 500m of grid point 0")
