#!/usr/bin/env python3
"""CLI for comparing different kernel configurations side-by-side."""
import argparse
import json
from pathlib import Path
import time

from config import Config, BBox, KernelConfig, KernelType, GridConfig
from extractor import extract_data
from indexer import create_spatial_index
from scorer import score_grid_points, normalize_scores
from output import generate_geojson, generate_comparison_html


def parse_config_string(config_str: str) -> tuple[str, KernelConfig]:
    """
    Parse config string like "exp150:exponential:150" or "power:power_law:2:50"
    Returns (name, KernelConfig)
    """
    parts = config_str.split(":")
    name = parts[0]

    if parts[1] == "exponential":
        lambda_m = float(parts[2])
        return name, KernelConfig(
            kernel_type=KernelType.EXPONENTIAL,
            lambda_m=lambda_m
        )
    elif parts[1] == "power_law":
        p = float(parts[2])
        d0_m = float(parts[3]) if len(parts) > 3 else 50.0
        return name, KernelConfig(
            kernel_type=KernelType.POWER_LAW,
            p=p,
            d0_m=d0_m
        )
    else:
        raise ValueError(f"Unknown kernel type: {parts[1]}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare different kernel configurations side-by-side"
    )
    parser.add_argument("--pbf", required=True, help="Path to OSM PBF file")
    parser.add_argument("--bbox", required=True,
                        help="Bounding box: min_lon,min_lat,max_lon,max_lat")
    parser.add_argument("--configs", nargs="+", required=True,
                        help="Config strings: name:kernel:params (e.g., 'exp150:exponential:150')")
    parser.add_argument("--rmax", type=float, default=1000.0,
                        help="Maximum influence radius (meters)")
    parser.add_argument("--ntarget", type=int, default=8000,
                        help="Target number of grid points")
    parser.add_argument("--out", default="output_compare",
                        help="Output directory")
    parser.add_argument("--tile-url",
                        default="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                        help="Map tile URL template")

    args = parser.parse_args()

    bbox = BBox.from_string(args.bbox)
    grid_config = GridConfig(n_target=args.ntarget, s_min=15.0, s_max=75.0)

    configs = [parse_config_string(c) for c in args.configs]

    print("=" * 60)
    print("Friendliness Index Comparison")
    print("=" * 60)
    print(f"PBF: {args.pbf}")
    print(f"BBox: {bbox.to_tuple()}")
    print(f"Configs: {[name for name, _ in configs]}")
    print("=" * 60)

    start_total = time.time()

    print("\n[1] Extracting data (shared across all configs)...")
    start = time.time()
    pois, walk_net = extract_data(args.pbf, bbox, buffer_m=args.rmax)
    print(f"  Done in {time.time() - start:.1f}s")

    print("\n[2] Building spatial index...")
    start = time.time()
    index = create_spatial_index(pois, walk_net, bbox, grid_config)
    print(f"  Done in {time.time() - start:.1f}s")

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    all_scores = []

    for i, (name, kernel_config) in enumerate(configs):
        print(f"\n[3.{i+1}] Scoring with config '{name}'...")
        print(f"  Kernel: {kernel_config.kernel_type.value}")
        if kernel_config.kernel_type == KernelType.EXPONENTIAL:
            print(f"  Lambda: {kernel_config.lambda_m}m")
        else:
            print(f"  p={kernel_config.p}, d0={kernel_config.d0_m}m")

        start = time.time()
        scores = score_grid_points(index, kernel_config, args.rmax, parallel=False)
        print(f"  Done in {time.time() - start:.1f}s")
        print(f"  Stats: min={scores.min():.2f}, max={scores.max():.2f}, mean={scores.mean():.2f}")

        all_scores.append(scores)
        results.append({
            "name": name,
            "kernel_config": kernel_config,
            "scores": scores
        })

    print("\n[4] Normalizing scores (shared scale)...")
    import numpy as np
    combined = np.concatenate(all_scores)
    global_max = combined.max()
    global_min = combined.min()

    for result in results:
        if global_max > global_min:
            result["scores_display"] = (np.log1p(result["scores"]) - np.log1p(global_min)) / (np.log1p(global_max) - np.log1p(global_min))
        else:
            result["scores_display"] = np.zeros_like(result["scores"])

    print("\n[5] Writing output files...")
    panel_configs = []
    for result in results:
        name = result["name"]
        geojson = generate_geojson(index, result["scores"], result["scores_display"])
        geojson_path = output_dir / f"{name}.geojson"
        with open(geojson_path, "w") as f:
            json.dump(geojson, f)
        print(f"  Wrote {name}.geojson")

        kc = result["kernel_config"]
        if kc.kernel_type == KernelType.EXPONENTIAL:
            label = f"{name} (exp λ={kc.lambda_m}m)"
        else:
            label = f"{name} (pow p={kc.p})"

        panel_configs.append({
            "name": name,
            "label": label,
            "geojson": f"{name}.geojson"
        })

    html = generate_comparison_html(args.tile_url, bbox, panel_configs, index.grid_spacing)
    with open(output_dir / "index.html", "w") as f:
        f.write(html)
    print("  Wrote index.html")

    metadata = {
        "bbox": bbox.to_tuple(),
        "r_max_m": args.rmax,
        "n_grid_points": len(index.grid_wgs),
        "n_pois": len(index.pois),
        "configs": [
            {
                "name": r["name"],
                "kernel_type": r["kernel_config"].kernel_type.value,
                "lambda_m": r["kernel_config"].lambda_m,
                "p": r["kernel_config"].p,
                "d0_m": r["kernel_config"].d0_m,
                "score_min": float(r["scores"].min()),
                "score_max": float(r["scores"].max()),
                "score_mean": float(r["scores"].mean()),
            }
            for r in results
        ]
    }
    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print("  Wrote metadata.json")

    print(f"\nTotal time: {time.time() - start_total:.1f}s")
    print(f"\nTo view comparison:")
    print(f"  cd {output_dir} && python -m http.server 8002")
    print(f"  Open http://localhost:8002")


if __name__ == "__main__":
    main()
