#!/usr/bin/env python3
"""CLI for generating friendliness index maps."""
import argparse
import warnings

warnings.filterwarnings("ignore", category=FutureWarning, module="pyrosm")
from pathlib import Path
import time

from config import Config, BBox, KernelConfig, KernelType, GridConfig, StreetsConfig
from extractor import extract_data
from indexer import create_spatial_index, build_walk_graph, snap_pois_to_edges
from scorer import score_grid_points, score_grid_points_euclidean, normalize_scores, score_street_segments
from output import write_output, write_streets_output


def main():
    parser = argparse.ArgumentParser(
        description="Generate friendliness index map from OSM data"
    )
    parser.add_argument("--pbf", required=True, help="Path to OSM PBF file")
    parser.add_argument("--bbox", required=True,
                        help="Bounding box: min_lon,min_lat,max_lon,max_lat")
    parser.add_argument("--kernel", choices=["exponential", "power_law"],
                        default="exponential", help="Kernel type")
    parser.add_argument("--lambda", dest="lambda_m", type=float, default=300.0,
                        help="Lambda for exponential kernel (meters)")
    parser.add_argument("--p", type=float, default=2.0,
                        help="Exponent for power law kernel")
    parser.add_argument("--d0", type=float, default=50.0,
                        help="Softening distance for power law kernel (meters)")
    parser.add_argument("--rmax", type=float, default=1500.0,
                        help="Maximum influence radius (meters)")
    parser.add_argument("--cell-size", type=float, default=50.0,
                        help="Grid cell width in meters")
    parser.add_argument("--out", default="output",
                        help="Output directory")
    parser.add_argument("--normalize", choices=["log1p", "quantile"],
                        default="log1p", help="Score normalization method")
    parser.add_argument("--tile-url",
                        default="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                        help="Map tile URL template")
    parser.add_argument("--parallel", action="store_true", default=False,
                        help="Use parallel processing (experimental, often slower)")
    parser.add_argument("--no-parallel", dest="parallel", action="store_false",
                        help="Disable parallel processing (default)")
    parser.add_argument("--distance", choices=["network", "euclidean"], default="network",
                        help="Distance mode: 'network' (walk graph) or 'euclidean' (straight line)")
    parser.add_argument("--max-snap", type=float, default=75.0,
                        help="Max distance (m) from grid point to graph edge; further points score 0")
    parser.add_argument("--export-graph", action="store_true",
                        help="Export walk graph as graph.geojson (can be large)")
    parser.add_argument("--mode", choices=["grid", "streets"], default="grid",
                        help="Visualization mode: 'grid' (2D heatmap) or 'streets' (1D heat-streets)")
    parser.add_argument("--intersection-penalty", type=float, default=50.0,
                        help="Extra distance (m) added when crossing intersections (streets mode)")
    parser.add_argument("--segment-length", type=float, default=10.0,
                        help="Target segment length (m) for street visualization")
    parser.add_argument("--output-format", choices=["geojson", "binary"], default="geojson",
                        help="Output format: 'geojson' (standard) or 'binary' (compact)")

    args = parser.parse_args()

    bbox = BBox.from_string(args.bbox)

    kernel_type = KernelType(args.kernel)
    kernel_config = KernelConfig(
        kernel_type=kernel_type,
        lambda_m=args.lambda_m,
        p=args.p,
        d0_m=args.d0
    )

    grid_config = GridConfig(
        cell_size_m=args.cell_size
    )

    streets_config = StreetsConfig(
        intersection_penalty_m=args.intersection_penalty,
        segment_length_m=args.segment_length
    )

    config = Config(
        kernel=kernel_config,
        grid=grid_config,
        streets=streets_config,
        r_max_m=args.rmax,
        tile_url=args.tile_url
    )

    print("=" * 60)
    print("Friendliness Index Generator")
    print("=" * 60)
    print(f"PBF: {args.pbf}")
    print(f"BBox: {bbox.to_tuple()}")
    print(f"Mode: {args.mode}")
    print(f"Kernel: {kernel_type.value}, lambda={args.lambda_m}m")
    if args.mode == "grid":
        print(f"Distance: {args.distance}")
        print(f"Cell size: {args.cell_size}m")
    else:
        print(f"Intersection penalty: {args.intersection_penalty}m")
        print(f"Segment length: {args.segment_length}m")
    print(f"R_max: {args.rmax}m")
    print(f"Output format: {args.output_format}")
    print("=" * 60)

    start_total = time.time()

    print("\n[1/4] Extracting data...")
    start = time.time()
    pois, walk_net = extract_data(args.pbf, bbox, buffer_m=args.rmax)
    print(f"  Done in {time.time() - start:.1f}s")

    if args.mode == "streets":
        print("\n[2/4] Building walk graph...")
        start = time.time()
        G = build_walk_graph(walk_net)
        print(f"  Done in {time.time() - start:.1f}s")

        print("\n[3/4] Snapping POIs to edges and computing scores...")
        start = time.time()
        edge_snapped_pois = snap_pois_to_edges(pois, G, bbox)
        print(f"  Snapped {len(edge_snapped_pois)} POIs to edges")

        segment_scores = score_street_segments(
            G, edge_snapped_pois, kernel_config, args.rmax,
            args.intersection_penalty, args.segment_length
        )

        n_segments = sum(len(segs) for segs in segment_scores.values())
        n_with_score = sum(1 for segs in segment_scores.values() for s in segs if s["score"] > 0)
        print(f"  {n_segments} segments, {n_with_score} with score > 0")
        print(f"  Done in {time.time() - start:.1f}s")

        print("\n[4/4] Generating output...")
        output_dir = Path(args.out)
        write_streets_output(output_dir, segment_scores, pois, bbox, config,
                             output_format=args.output_format)

    else:
        print("\n[2/4] Building spatial index...")
        start = time.time()
        index = create_spatial_index(pois, walk_net, bbox, grid_config)
        print(f"  Done in {time.time() - start:.1f}s")

        print(f"\n[3/4] Computing scores ({args.distance} distance)...")
        start = time.time()
        if args.distance == "euclidean":
            scores = score_grid_points_euclidean(index, kernel_config, args.rmax)
        else:
            scores = score_grid_points(index, kernel_config, args.rmax,
                                       parallel=args.parallel, max_snap_distance_m=args.max_snap)
        print(f"  Done in {time.time() - start:.1f}s")

        print(f"\n  Score stats: min={scores.min():.2f}, max={scores.max():.2f}, mean={scores.mean():.2f}")

        print("\n[4/4] Generating output...")
        scores_display = normalize_scores(scores, args.normalize)
        output_dir = Path(args.out)
        graph = index.G if args.export_graph else None
        write_output(output_dir, index, scores, scores_display, bbox, config, graph=graph,
                     output_format=args.output_format)

    print(f"\nTotal time: {time.time() - start_total:.1f}s")
    print(f"\nTo view the map:")
    print(f"  cd {output_dir} && python -m http.server 8000")
    print(f"  Open http://localhost:8000")


if __name__ == "__main__":
    main()
