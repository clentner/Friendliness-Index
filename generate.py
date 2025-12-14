#!/usr/bin/env python3
"""CLI for generating friendliness index maps."""
import argparse
from pathlib import Path
import time

from config import Config, BBox, KernelConfig, KernelType, GridConfig
from extractor import extract_data
from indexer import create_spatial_index
from scorer import score_grid_points, score_grid_points_euclidean, normalize_scores
from output import write_output


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
    parser.add_argument("--ntarget", type=int, default=10000,
                        help="Target number of grid points")
    parser.add_argument("--smin", type=float, default=15.0,
                        help="Minimum grid spacing (meters)")
    parser.add_argument("--smax", type=float, default=75.0,
                        help="Maximum grid spacing (meters)")
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
        n_target=args.ntarget,
        s_min=args.smin,
        s_max=args.smax
    )

    config = Config(
        kernel=kernel_config,
        grid=grid_config,
        r_max_m=args.rmax,
        tile_url=args.tile_url
    )

    print("=" * 60)
    print("Friendliness Index Generator")
    print("=" * 60)
    print(f"PBF: {args.pbf}")
    print(f"BBox: {bbox.to_tuple()}")
    print(f"Kernel: {kernel_type.value}, lambda={args.lambda_m}m")
    print(f"Distance: {args.distance}")
    print(f"R_max: {args.rmax}m")
    print(f"Grid target: {args.ntarget} points")
    print("=" * 60)

    start_total = time.time()

    print("\n[1/4] Extracting data...")
    start = time.time()
    pois, walk_net = extract_data(args.pbf, bbox, buffer_m=args.rmax)
    print(f"  Done in {time.time() - start:.1f}s")

    print("\n[2/4] Building spatial index...")
    start = time.time()
    index = create_spatial_index(pois, walk_net, bbox, grid_config)
    print(f"  Done in {time.time() - start:.1f}s")

    print(f"\n[3/4] Computing scores ({args.distance} distance)...")
    start = time.time()
    if args.distance == "euclidean":
        scores = score_grid_points_euclidean(index, kernel_config, args.rmax)
    else:
        scores = score_grid_points(index, kernel_config, args.rmax, parallel=args.parallel)
    print(f"  Done in {time.time() - start:.1f}s")

    print(f"\n  Score stats: min={scores.min():.2f}, max={scores.max():.2f}, mean={scores.mean():.2f}")

    print("\n[4/4] Generating output...")
    scores_display = normalize_scores(scores, args.normalize)
    output_dir = Path(args.out)
    write_output(output_dir, index, scores, scores_display, bbox, config)

    print(f"\nTotal time: {time.time() - start_total:.1f}s")
    print(f"\nTo view the map:")
    print(f"  cd {output_dir} && python -m http.server 8000")
    print(f"  Open http://localhost:8000")


if __name__ == "__main__":
    main()
