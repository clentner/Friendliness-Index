"""Data extraction from OSM PBF files."""
import json
from pathlib import Path
from typing import Optional
import geopandas as gpd
import numpy as np
import pandas as pd
from pyrosm import OSM
from shapely.geometry import Point
from config import BBox


def load_poi_config(config_path: str = "poi_config.json") -> dict:
    """Load POI allow/deny configuration."""
    with open(config_path) as f:
        return json.load(f)


def filter_pois(pois: gpd.GeoDataFrame, poi_config: dict) -> gpd.GeoDataFrame:
    """Filter POIs based on allow/deny configuration."""
    allow = poi_config.get("allow", {})
    deny = poi_config.get("deny", {})

    mask = np.zeros(len(pois), dtype=bool)

    for tag, values in allow.items():
        if tag not in pois.columns:
            continue
        col = pois[tag]
        if values == ["*"]:
            mask |= col.notna()
        else:
            mask |= col.isin(values)

    for tag, values in deny.items():
        if tag not in pois.columns:
            continue
        col = pois[tag]
        mask &= ~col.isin(values)

    return pois[mask].copy()


def pois_to_points(pois: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Convert POI geometries to representative points."""
    result = pois.copy()
    geom_types = result.geometry.geom_type

    poly_mask = geom_types.isin(["Polygon", "MultiPolygon"])
    if poly_mask.any():
        result.loc[poly_mask, "geometry"] = result.loc[poly_mask].geometry.representative_point()

    line_mask = geom_types.isin(["LineString", "MultiLineString"])
    if line_mask.any():
        result.loc[line_mask, "geometry"] = result.loc[line_mask].geometry.centroid

    return result


def extract_data(pbf_path: str, bbox: BBox, buffer_m: float = 1500.0,
                 poi_config_path: str = "poi_config.json") -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Extract POIs and walk network from PBF file.

    Args:
        pbf_path: Path to OSM PBF file
        bbox: Bounding box for extraction
        buffer_m: Buffer distance in meters for edge artifact prevention
        poi_config_path: Path to POI filter configuration

    Returns:
        Tuple of (filtered_pois, walk_network)
    """
    buffered_bbox = bbox.buffer_degrees(buffer_m)
    bbox_list = [buffered_bbox.min_lon, buffered_bbox.min_lat,
                 buffered_bbox.max_lon, buffered_bbox.max_lat]

    print(f"Loading PBF with buffered bbox: {bbox_list}")
    osm = OSM(pbf_path, bounding_box=bbox_list)

    print("Extracting walk network...")
    walk_net = osm.get_network(network_type="walking")
    print(f"Walk network: {len(walk_net)} edges")

    if "access" in walk_net.columns:
        access_no_count = (walk_net["access"] == "no").sum()
        if access_no_count > 0:
            walk_net = walk_net[walk_net["access"] != "no"].copy()
            print(f"Removed {access_no_count} edges with access=no")

    corridors = osm.get_data_by_custom_criteria(
        custom_filter={"highway": ["corridor"]},
        filter_type="keep"
    )
    if corridors is not None and len(corridors) > 0:
        print(f"Indoor corridors: {len(corridors)} edges")
        walk_net = gpd.GeoDataFrame(pd.concat([walk_net, corridors], ignore_index=True))
        print(f"Combined walk network: {len(walk_net)} edges")

    print("Extracting POIs...")
    pois = osm.get_pois()
    print(f"Raw POIs: {len(pois)}")

    poi_config = load_poi_config(poi_config_path)
    filtered_pois = filter_pois(pois, poi_config)
    print(f"Filtered POIs: {len(filtered_pois)}")

    point_pois = pois_to_points(filtered_pois)

    return point_pois, walk_net


if __name__ == "__main__":
    test_bbox = BBox.from_string("-71.065,42.355,-71.055,42.362")
    pois, walk_net = extract_data(
        "massachusetts-251213.osm.pbf",
        test_bbox,
        buffer_m=500.0
    )
    print(f"\nExtracted {len(pois)} POIs and {len(walk_net)} walk edges")
    print(f"POI geometry types: {pois.geometry.geom_type.value_counts().to_dict()}")
    print(f"\nSample POIs:")
    for col in ["amenity", "shop", "tourism"]:
        if col in pois.columns:
            vals = pois[col].dropna().value_counts().head(5)
            if len(vals) > 0:
                print(f"  {col}: {vals.to_dict()}")
