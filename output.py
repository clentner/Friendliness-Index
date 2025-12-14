"""Output generation: GeoJSON and static viewer."""
import json
from pathlib import Path
from datetime import datetime
import numpy as np
from indexer import SpatialIndex
from config import Config, BBox


def generate_geojson(index: SpatialIndex, scores: np.ndarray,
                     scores_display: np.ndarray) -> dict:
    """Generate GeoJSON FeatureCollection with grid cell polygons."""
    from pyproj import Transformer

    features = []

    half_spacing = index.grid_spacing / 2.0
    to_wgs = Transformer.from_crs(index.utm_crs, "EPSG:4326", always_xy=True)

    for i, (lon, lat) in enumerate(index.grid_wgs):
        utm_x, utm_y = index.to_utm.transform(lon, lat)

        corners_utm = [
            (utm_x - half_spacing, utm_y - half_spacing),
            (utm_x + half_spacing, utm_y - half_spacing),
            (utm_x + half_spacing, utm_y + half_spacing),
            (utm_x - half_spacing, utm_y + half_spacing),
            (utm_x - half_spacing, utm_y - half_spacing),
        ]
        corners_wgs = [to_wgs.transform(x, y) for x, y in corners_utm]

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[c[0], c[1]] for c in corners_wgs]]
            },
            "properties": {
                "score": float(scores[i]),
                "score_display": float(scores_display[i])
            }
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features
    }


def generate_metadata(bbox: BBox, config: Config, n_pois: int, n_grid: int,
                      scores: np.ndarray) -> dict:
    """Generate run metadata."""
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "bbox": bbox.to_tuple(),
        "config": config.to_dict(),
        "stats": {
            "n_pois": n_pois,
            "n_grid_points": n_grid,
            "score_min": float(scores.min()),
            "score_max": float(scores.max()),
            "score_mean": float(scores.mean()),
            "score_std": float(scores.std()),
        }
    }


def generate_viewer_html(tile_url: str, bbox: BBox, grid_spacing: float) -> str:
    """Generate the HTML viewer with proper heatmap layer."""
    center_lon = (bbox.min_lon + bbox.max_lon) / 2
    center_lat = (bbox.min_lat + bbox.max_lat) / 2

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Friendliness Index Map</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://unpkg.com/maplibre-gl@4.0.0/dist/maplibre-gl.css" rel="stylesheet" />
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        #legend {{
            position: absolute;
            bottom: 30px;
            left: 10px;
            background: white;
            padding: 10px 15px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            font-family: sans-serif;
            font-size: 12px;
        }}
        #legend h4 {{ margin: 0 0 8px 0; font-size: 14px; }}
        .legend-scale {{ height: 15px; width: 150px; margin-bottom: 4px; }}
        .legend-labels {{ display: flex; justify-content: space-between; width: 150px; font-size: 10px; }}
        #info {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: white;
            padding: 10px 15px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            font-family: sans-serif;
            font-size: 12px;
            max-width: 300px;
        }}
        #info h3 {{ margin: 0 0 8px 0; }}
        #info p {{ margin: 4px 0; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="info">
        <h3>Friendliness Index</h3>
        <p id="hover-info">Click on map for score details</p>
        <p id="stats"></p>
    </div>
    <div id="legend">
        <h4>Friendliness</h4>
        <div class="legend-scale" id="gradient"></div>
        <div class="legend-labels"><span>Low</span><span>High</span></div>
    </div>
    <script src="https://unpkg.com/maplibre-gl@4.0.0/dist/maplibre-gl.js"></script>
    <script>
        const GRID_SPACING_M = {grid_spacing};

        const map = new maplibregl.Map({{
            container: 'map',
            style: {{
                version: 8,
                sources: {{
                    osm: {{
                        type: 'raster',
                        tiles: ['{tile_url}'],
                        tileSize: 256,
                        attribution: '&copy; OpenStreetMap contributors'
                    }}
                }},
                layers: [{{
                    id: 'osm-tiles',
                    type: 'raster',
                    source: 'osm',
                    minzoom: 0,
                    maxzoom: 19
                }}]
            }},
            center: [{center_lon}, {center_lat}],
            zoom: 14
        }});

        map.addControl(new maplibregl.NavigationControl());

        const gradient = document.getElementById('gradient');
        gradient.style.background = 'linear-gradient(to right, #313695, #4575b4, #74add1, #abd9e9, #fee090, #fdae61, #f46d43, #a50026)';

        map.on('load', function() {{
            fetch('results.geojson')
                .then(response => response.json())
                .then(data => {{
                    // Compute score range for display
                    const scores = data.features.map(f => f.properties.score);
                    const minScore = Math.min(...scores);
                    const maxScore = Math.max(...scores);
                    document.getElementById('stats').innerHTML =
                        `Range: ${{minScore.toFixed(1)}} - ${{maxScore.toFixed(1)}}`;

                    map.addSource('scores', {{
                        type: 'geojson',
                        data: data
                    }});

                    // Fill layer for grid cells - colors stay consistent across zoom
                    map.addLayer({{
                        id: 'score-fill',
                        type: 'fill',
                        source: 'scores',
                        paint: {{
                            'fill-color': [
                                'interpolate', ['linear'], ['get', 'score_display'],
                                0, '#313695',
                                0.15, '#4575b4',
                                0.3, '#74add1',
                                0.45, '#abd9e9',
                                0.55, '#fee090',
                                0.7, '#fdae61',
                                0.85, '#f46d43',
                                1, '#a50026'
                            ],
                            'fill-opacity': 0.7
                        }}
                    }});

                    // Outline layer for grid cells (visible when zoomed in)
                    map.addLayer({{
                        id: 'score-outline',
                        type: 'line',
                        source: 'scores',
                        minzoom: 15,
                        paint: {{
                            'line-color': '#333',
                            'line-width': 0.5,
                            'line-opacity': [
                                'interpolate', ['linear'], ['zoom'],
                                15, 0,
                                17, 0.3
                            ]
                        }}
                    }});

                    // Click for details
                    map.on('click', 'score-fill', (e) => {{
                        if (e.features.length > 0) {{
                            const props = e.features[0].properties;
                            document.getElementById('hover-info').innerHTML =
                                `<b>Score:</b> ${{props.score.toFixed(2)}}<br>` +
                                `<b>Normalized:</b> ${{(props.score_display * 100).toFixed(1)}}%`;
                        }}
                    }});

                    // Change cursor on hover
                    map.on('mouseenter', 'score-fill', () => {{
                        map.getCanvas().style.cursor = 'pointer';
                    }});
                    map.on('mouseleave', 'score-fill', () => {{
                        map.getCanvas().style.cursor = '';
                    }});

                    // Fit to data bounds
                    const bounds = new maplibregl.LngLatBounds();
                    data.features.forEach(f => {{
                        f.geometry.coordinates[0].forEach(c => bounds.extend(c));
                    }});
                    map.fitBounds(bounds, {{ padding: 50 }});
                }});
        }});
    </script>
</body>
</html>'''


def write_output(output_dir: Path, index: SpatialIndex, scores: np.ndarray,
                 scores_display: np.ndarray, bbox: BBox, config: Config) -> None:
    """Write all output files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    geojson = generate_geojson(index, scores, scores_display)
    with open(output_dir / "results.geojson", "w") as f:
        json.dump(geojson, f)
    print(f"Wrote {len(geojson['features'])} features to results.geojson")

    metadata = generate_metadata(bbox, config, len(index.pois), len(index.grid_wgs), scores)
    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print("Wrote metadata.json")

    html = generate_viewer_html(config.tile_url, bbox, index.grid_spacing)
    with open(output_dir / "index.html", "w") as f:
        f.write(html)
    print("Wrote index.html")

    print(f"\nOutput written to {output_dir}/")
    print(f"To view: cd {output_dir} && python -m http.server 8000")
