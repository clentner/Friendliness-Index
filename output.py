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


def generate_poi_geojson(index: SpatialIndex) -> dict:
    """Generate GeoJSON FeatureCollection for POI markers."""
    import geopandas as gpd

    features = []
    tag_cols = ["name", "amenity", "shop", "tourism", "leisure"]

    for idx, row in index.pois.iterrows():
        geom = row.geometry
        if geom is None:
            continue

        props = {}
        for col in tag_cols:
            if col in index.pois.columns:
                val = row.get(col)
                if val is not None and str(val) != "nan":
                    props[col] = str(val)

        if not any(k in props for k in ["amenity", "shop", "tourism", "leisure"]):
            continue

        poi_type = props.get("amenity") or props.get("shop") or props.get("tourism") or props.get("leisure") or "unknown"
        props["type"] = poi_type

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(geom.x), float(geom.y)]
            },
            "properties": props
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features
    }


def generate_streets_geojson(segment_scores: dict, scores_display: dict) -> dict:
    """
    Generate GeoJSON FeatureCollection for street segments with scores.

    Args:
        segment_scores: Dict from score_street_segments()
        scores_display: Dict mapping (edge, seg_idx) to normalized score
    """
    features = []

    for edge_key, segments in segment_scores.items():
        for i, seg in enumerate(segments):
            score = seg["score"]
            display_key = (edge_key, i)
            score_display = scores_display.get(display_key, 0.0)

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [seg["start"][0], seg["start"][1]],
                        [seg["end"][0], seg["end"][1]]
                    ]
                },
                "properties": {
                    "score": float(score),
                    "score_display": float(score_display)
                }
            }
            features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features
    }


def normalize_segment_scores(segment_scores: dict, method: str = "log1p") -> dict:
    """
    Normalize segment scores for display.

    Returns dict mapping (edge_key, segment_idx) -> normalized score.
    """
    all_scores = []
    for edge_key, segments in segment_scores.items():
        for seg in segments:
            all_scores.append(seg["score"])

    all_scores = np.array(all_scores)

    if method == "log1p":
        normalized = np.log1p(all_scores)
    else:
        normalized = all_scores.copy()

    if normalized.max() > normalized.min():
        normalized = (normalized - normalized.min()) / (normalized.max() - normalized.min())

    result = {}
    idx = 0
    for edge_key, segments in segment_scores.items():
        for i, seg in enumerate(segments):
            result[(edge_key, i)] = float(normalized[idx])
            idx += 1

    return result


def generate_graph_geojson(G) -> dict:
    """Generate GeoJSON FeatureCollection for walk graph edges."""
    features = []

    for u, v, data in G.edges(data=True):
        weight = data.get("weight", 0)

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[u[0], u[1]], [v[0], v[1]]]
            },
            "properties": {
                "length_m": round(weight, 1)
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
        #controls {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 10px 15px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            font-family: sans-serif;
            font-size: 12px;
        }}
        #controls label {{ cursor: pointer; }}
        .poi-popup {{ font-family: sans-serif; font-size: 12px; }}
        .poi-popup b {{ color: #333; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="info">
        <h3>Friendliness Index</h3>
        <p id="hover-info">Click on map for score details</p>
        <p id="stats"></p>
    </div>
    <div id="controls">
        <label><input type="checkbox" id="toggle-pois"> Show POIs</label>
        <label style="margin-left: 15px;"><input type="checkbox" id="toggle-graph"> Show Walk Graph</label>
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
                    // Compute score range for display (use reduce to avoid stack overflow on large arrays)
                    const scores = data.features.map(f => f.properties.score);
                    const minScore = scores.reduce((a, b) => a < b ? a : b, Infinity);
                    const maxScore = scores.reduce((a, b) => a > b ? a : b, -Infinity);
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

            // Load POIs
            fetch('pois.geojson')
                .then(response => response.json())
                .then(poiData => {{
                    map.addSource('pois', {{
                        type: 'geojson',
                        data: poiData
                    }});

                    // Named POIs - solid purple circles
                    map.addLayer({{
                        id: 'poi-named',
                        type: 'circle',
                        source: 'pois',
                        filter: ['has', 'name'],
                        layout: {{
                            'visibility': 'none'
                        }},
                        paint: {{
                            'circle-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                10, 3,
                                14, 5,
                                18, 9
                            ],
                            'circle-color': '#9b27b0',
                            'circle-stroke-color': '#fff',
                            'circle-stroke-width': 1.5,
                            'circle-opacity': 0.9
                        }}
                    }});

                    // Unnamed POIs - hollow orange circles (smaller)
                    map.addLayer({{
                        id: 'poi-unnamed',
                        type: 'circle',
                        source: 'pois',
                        filter: ['!', ['has', 'name']],
                        layout: {{
                            'visibility': 'none'
                        }},
                        paint: {{
                            'circle-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                10, 2,
                                14, 3,
                                18, 6
                            ],
                            'circle-color': 'transparent',
                            'circle-stroke-color': '#ff9800',
                            'circle-stroke-width': 2,
                            'circle-opacity': 0.8
                        }}
                    }});

                    // POI click popup (for both layers)
                    const poiClickHandler = (e) => {{
                        if (e.features.length > 0) {{
                            const props = e.features[0].properties;
                            const coords = e.features[0].geometry.coordinates;
                            let html = '<div class="poi-popup">';
                            if (props.name) {{
                                html += `<b>${{props.name}}</b><br>`;
                            }} else {{
                                html += `<b style="color:#ff9800">(unnamed)</b><br>`;
                            }}
                            html += `<b>Type:</b> ${{props.type}}<br>`;
                            if (props.amenity) html += `amenity=${{props.amenity}}<br>`;
                            if (props.shop) html += `shop=${{props.shop}}<br>`;
                            if (props.tourism) html += `tourism=${{props.tourism}}<br>`;
                            if (props.leisure) html += `leisure=${{props.leisure}}<br>`;
                            html += '</div>';

                            new maplibregl.Popup()
                                .setLngLat(coords)
                                .setHTML(html)
                                .addTo(map);
                        }}
                    }};
                    map.on('click', 'poi-named', poiClickHandler);
                    map.on('click', 'poi-unnamed', poiClickHandler);

                    ['poi-named', 'poi-unnamed'].forEach(layer => {{
                        map.on('mouseenter', layer, () => {{
                            map.getCanvas().style.cursor = 'pointer';
                        }});
                        map.on('mouseleave', layer, () => {{
                            map.getCanvas().style.cursor = '';
                        }});
                    }});

                    // Toggle POI visibility
                    document.getElementById('toggle-pois').addEventListener('change', (e) => {{
                        const vis = e.target.checked ? 'visible' : 'none';
                        map.setLayoutProperty('poi-named', 'visibility', vis);
                        map.setLayoutProperty('poi-unnamed', 'visibility', vis);
                    }});
                }})
                .catch(err => console.log('No POI data available'));

            // Load walk graph (optional)
            fetch('graph.geojson')
                .then(response => response.json())
                .then(graphData => {{
                    map.addSource('graph', {{
                        type: 'geojson',
                        data: graphData
                    }});

                    // Graph edges layer - thin gray lines
                    map.addLayer({{
                        id: 'graph-edges',
                        type: 'line',
                        source: 'graph',
                        layout: {{
                            'visibility': 'none'
                        }},
                        paint: {{
                            'line-color': '#666',
                            'line-width': 1,
                            'line-opacity': 0.6
                        }}
                    }}, 'score-fill');  // Insert below the heatmap

                    // Toggle graph visibility
                    document.getElementById('toggle-graph').addEventListener('change', (e) => {{
                        const vis = e.target.checked ? 'visible' : 'none';
                        map.setLayoutProperty('graph-edges', 'visibility', vis);
                    }});
                }})
                .catch(err => console.log('No graph data available'));
        }});
    </script>
</body>
</html>'''


def generate_streets_viewer_html(tile_url: str, bbox: BBox) -> str:
    """Generate the HTML viewer for heat-streets visualization."""
    center_lon = (bbox.min_lon + bbox.max_lon) / 2
    center_lat = (bbox.min_lat + bbox.max_lat) / 2

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Heat-Streets Map</title>
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
        #controls {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 10px 15px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            font-family: sans-serif;
            font-size: 12px;
        }}
        #controls label {{ cursor: pointer; }}
        .poi-popup {{ font-family: sans-serif; font-size: 12px; }}
        .poi-popup b {{ color: #333; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="info">
        <h3>Heat-Streets</h3>
        <p id="hover-info">Click on a street for score details</p>
        <p id="stats"></p>
    </div>
    <div id="controls">
        <label><input type="checkbox" id="toggle-pois"> Show POIs</label>
    </div>
    <div id="legend">
        <h4>Friendliness</h4>
        <div class="legend-scale" id="gradient"></div>
        <div class="legend-labels"><span>Low</span><span>High</span></div>
    </div>
    <script src="https://unpkg.com/maplibre-gl@4.0.0/dist/maplibre-gl.js"></script>
    <script>
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
            fetch('streets.geojson')
                .then(response => response.json())
                .then(data => {{
                    const scores = data.features.map(f => f.properties.score);
                    const minScore = scores.reduce((a, b) => a < b ? a : b, Infinity);
                    const maxScore = scores.reduce((a, b) => a > b ? a : b, -Infinity);
                    const nonZeroCount = scores.filter(s => s > 0).length;
                    document.getElementById('stats').innerHTML =
                        `Range: ${{minScore.toFixed(1)}} - ${{maxScore.toFixed(1)}}<br>` +
                        `Segments with score: ${{nonZeroCount}} / ${{scores.length}}`;

                    map.addSource('streets', {{
                        type: 'geojson',
                        data: data
                    }});

                    map.addLayer({{
                        id: 'streets-line',
                        type: 'line',
                        source: 'streets',
                        paint: {{
                            'line-color': [
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
                            'line-width': [
                                'interpolate', ['linear'], ['zoom'],
                                10, 2,
                                14, 3,
                                18, 5
                            ],
                            'line-opacity': 0.85
                        }}
                    }});

                    map.on('click', 'streets-line', (e) => {{
                        if (e.features.length > 0) {{
                            const props = e.features[0].properties;
                            document.getElementById('hover-info').innerHTML =
                                `<b>Score:</b> ${{props.score.toFixed(2)}}<br>` +
                                `<b>Normalized:</b> ${{(props.score_display * 100).toFixed(1)}}%`;
                        }}
                    }});

                    map.on('mouseenter', 'streets-line', () => {{
                        map.getCanvas().style.cursor = 'pointer';
                    }});
                    map.on('mouseleave', 'streets-line', () => {{
                        map.getCanvas().style.cursor = '';
                    }});

                    const bounds = new maplibregl.LngLatBounds();
                    data.features.slice(0, 1000).forEach(f => {{
                        f.geometry.coordinates.forEach(c => bounds.extend(c));
                    }});
                    map.fitBounds(bounds, {{ padding: 50 }});
                }});

            fetch('pois.geojson')
                .then(response => response.json())
                .then(poiData => {{
                    map.addSource('pois', {{
                        type: 'geojson',
                        data: poiData
                    }});

                    map.addLayer({{
                        id: 'poi-markers',
                        type: 'circle',
                        source: 'pois',
                        layout: {{
                            'visibility': 'none'
                        }},
                        paint: {{
                            'circle-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                10, 3,
                                14, 5,
                                18, 8
                            ],
                            'circle-color': '#9b27b0',
                            'circle-stroke-color': '#fff',
                            'circle-stroke-width': 1.5,
                            'circle-opacity': 0.9
                        }}
                    }});

                    map.on('click', 'poi-markers', (e) => {{
                        if (e.features.length > 0) {{
                            const props = e.features[0].properties;
                            const coords = e.features[0].geometry.coordinates;
                            let html = '<div class="poi-popup">';
                            if (props.name) {{
                                html += `<b>${{props.name}}</b><br>`;
                            }}
                            html += `<b>Type:</b> ${{props.type}}<br>`;
                            html += '</div>';

                            new maplibregl.Popup()
                                .setLngLat(coords)
                                .setHTML(html)
                                .addTo(map);
                        }}
                    }});

                    document.getElementById('toggle-pois').addEventListener('change', (e) => {{
                        const vis = e.target.checked ? 'visible' : 'none';
                        map.setLayoutProperty('poi-markers', 'visibility', vis);
                    }});
                }})
                .catch(err => console.log('No POI data available'));
        }});
    </script>
</body>
</html>'''


def generate_comparison_html(tile_url: str, bbox: BBox, panel_configs: list, grid_spacing: float) -> str:
    """
    Generate side-by-side comparison viewer HTML.

    Args:
        tile_url: Map tile URL template
        bbox: Bounding box
        panel_configs: List of dicts with 'name', 'label', 'geojson' keys
        grid_spacing: Grid spacing in meters
    """
    center_lon = (bbox.min_lon + bbox.max_lon) / 2
    center_lat = (bbox.min_lat + bbox.max_lat) / 2
    n_panels = len(panel_configs)

    panels_json = json.dumps(panel_configs)

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Friendliness Index Comparison</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://unpkg.com/maplibre-gl@4.0.0/dist/maplibre-gl.css" rel="stylesheet" />
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; padding: 0; font-family: sans-serif; }}
        #container {{ display: flex; height: 100vh; width: 100vw; }}
        .panel {{ flex: 1; position: relative; border-right: 2px solid #333; }}
        .panel:last-child {{ border-right: none; }}
        .panel-header {{
            position: absolute;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            background: white;
            padding: 8px 16px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            font-weight: bold;
            font-size: 14px;
            z-index: 1000;
            white-space: nowrap;
        }}
        .map {{ width: 100%; height: 100%; }}
        #legend {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: white;
            padding: 10px 20px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        #legend .label {{ font-size: 12px; }}
        #legend .gradient {{ width: 200px; height: 15px; }}
        #score-display {{
            position: fixed;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            background: white;
            padding: 8px 16px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            z-index: 1000;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="score-display">Click a cell to compare scores</div>
    <div id="legend">
        <span class="label">Low</span>
        <div class="gradient" id="gradient"></div>
        <span class="label">High</span>
    </div>
    <script src="https://unpkg.com/maplibre-gl@4.0.0/dist/maplibre-gl.js"></script>
    <script>
        const PANELS = {panels_json};
        const TILE_URL = '{tile_url}';
        const CENTER = [{center_lon}, {center_lat}];
        const maps = [];
        let syncing = false;

        document.getElementById('gradient').style.background =
            'linear-gradient(to right, #313695, #4575b4, #74add1, #abd9e9, #fee090, #fdae61, #f46d43, #a50026)';

        const container = document.getElementById('container');

        PANELS.forEach((panel, idx) => {{
            const panelDiv = document.createElement('div');
            panelDiv.className = 'panel';
            panelDiv.innerHTML = `
                <div class="panel-header">${{panel.label}}</div>
                <div class="map" id="map-${{idx}}"></div>
            `;
            container.appendChild(panelDiv);
        }});

        PANELS.forEach((panel, idx) => {{
            const map = new maplibregl.Map({{
                container: `map-${{idx}}`,
                style: {{
                    version: 8,
                    sources: {{
                        osm: {{
                            type: 'raster',
                            tiles: [TILE_URL],
                            tileSize: 256,
                            attribution: '&copy; OpenStreetMap'
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
                center: CENTER,
                zoom: 13
            }});

            if (idx === 0) {{
                map.addControl(new maplibregl.NavigationControl());
            }}

            map.on('load', () => {{
                fetch(panel.geojson)
                    .then(r => r.json())
                    .then(data => {{
                        map.addSource('scores', {{ type: 'geojson', data: data }});

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

                        map.addLayer({{
                            id: 'score-outline',
                            type: 'line',
                            source: 'scores',
                            minzoom: 15,
                            paint: {{
                                'line-color': '#333',
                                'line-width': 0.5,
                                'line-opacity': ['interpolate', ['linear'], ['zoom'], 15, 0, 17, 0.3]
                            }}
                        }});

                        map.on('click', 'score-fill', (e) => {{
                            if (e.features.length > 0) {{
                                const props = e.features[0].properties;
                                const parts = PANELS.map((p, i) => `${{p.name}}: ${{props.score ? props.score.toFixed(2) : '?'}}`);
                                document.getElementById('score-display').innerHTML =
                                    `<b>Score:</b> ${{props.score.toFixed(2)}} | <b>Normalized:</b> ${{(props.score_display * 100).toFixed(1)}}%`;
                            }}
                        }});

                        if (idx === 0) {{
                            const bounds = new maplibregl.LngLatBounds();
                            data.features.slice(0, 100).forEach(f => {{
                                f.geometry.coordinates[0].forEach(c => bounds.extend(c));
                            }});
                            map.fitBounds(bounds, {{ padding: 30 }});
                        }}
                    }});
            }});

            // Sync maps
            map.on('move', () => {{
                if (syncing) return;
                syncing = true;
                const center = map.getCenter();
                const zoom = map.getZoom();
                const bearing = map.getBearing();
                const pitch = map.getPitch();
                maps.forEach((m, i) => {{
                    if (i !== idx) {{
                        m.setCenter(center);
                        m.setZoom(zoom);
                        m.setBearing(bearing);
                        m.setPitch(pitch);
                    }}
                }});
                syncing = false;
            }});

            maps.push(map);
        }});
    </script>
</body>
</html>'''


def generate_binary_streets_viewer_html(tile_url: str, bbox: BBox) -> str:
    """Generate HTML viewer that loads binary format street data."""
    center_lon = (bbox.min_lon + bbox.max_lon) / 2
    center_lat = (bbox.min_lat + bbox.max_lat) / 2

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Heat-Streets Map</title>
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
        #controls {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 10px 15px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            font-family: sans-serif;
            font-size: 12px;
        }}
        #controls label {{ cursor: pointer; }}
        #loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            padding: 20px 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            font-family: sans-serif;
            z-index: 1000;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="loading">Loading data...</div>
    <div id="info">
        <h3>Heat-Streets</h3>
        <p id="hover-info">Click on a street for score details</p>
        <p id="stats"></p>
    </div>
    <div id="controls">
        <label><input type="checkbox" id="toggle-pois"> Show POIs</label>
    </div>
    <div id="legend">
        <h4>Friendliness</h4>
        <div class="legend-scale" id="gradient"></div>
        <div class="legend-labels"><span>Low</span><span>High</span></div>
    </div>
    <script src="https://unpkg.com/maplibre-gl@4.0.0/dist/maplibre-gl.js"></script>
    <script>
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

        async function loadBinaryData() {{
            const meta = await fetch('streets.json').then(r => r.json());
            const buffer = await fetch('segments.bin').then(r => r.arrayBuffer());
            const data = new Float32Array(buffer);
            return {{ meta, data }};
        }}

        function generateFeatures(meta, data) {{
            const logMax = Math.log1p(meta.scores.max);
            const features = [];

            for (let i = 0; i < meta.segments.count; i++) {{
                const offset = i * 5;
                const startLon = data[offset];
                const startLat = data[offset + 1];
                const endLon = data[offset + 2];
                const endLat = data[offset + 3];
                const score = data[offset + 4];
                const normalized = logMax > 0 ? Math.log1p(score) / logMax : 0;

                features.push({{
                    type: 'Feature',
                    geometry: {{
                        type: 'LineString',
                        coordinates: [[startLon, startLat], [endLon, endLat]]
                    }},
                    properties: {{ score, score_display: normalized }}
                }});
            }}
            return {{ type: 'FeatureCollection', features }};
        }}

        map.on('load', async function() {{
            try {{
                const {{ meta, data }} = await loadBinaryData();
                document.getElementById('loading').style.display = 'none';

                document.getElementById('stats').innerHTML =
                    `Range: ${{meta.scores.min.toFixed(1)}} - ${{meta.scores.max.toFixed(1)}}<br>` +
                    `Segments: ${{meta.segments.count.toLocaleString()}}`;

                console.time('generateFeatures');
                const geojson = generateFeatures(meta, data);
                console.timeEnd('generateFeatures');

                map.addSource('streets', {{ type: 'geojson', data: geojson }});

                map.addLayer({{
                    id: 'streets-line',
                    type: 'line',
                    source: 'streets',
                    paint: {{
                        'line-color': [
                            'interpolate', ['linear'], ['get', 'score_display'],
                            0, '#313695', 0.15, '#4575b4', 0.3, '#74add1',
                            0.45, '#abd9e9', 0.55, '#fee090', 0.7, '#fdae61',
                            0.85, '#f46d43', 1, '#a50026'
                        ],
                        'line-width': ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 3, 18, 5],
                        'line-opacity': 0.85
                    }}
                }});

                map.on('click', 'streets-line', (e) => {{
                    if (e.features.length > 0) {{
                        const props = e.features[0].properties;
                        document.getElementById('hover-info').innerHTML =
                            `<b>Score:</b> ${{props.score.toFixed(2)}}<br>` +
                            `<b>Normalized:</b> ${{(props.score_display * 100).toFixed(1)}}%`;
                    }}
                }});

                map.on('mouseenter', 'streets-line', () => {{ map.getCanvas().style.cursor = 'pointer'; }});
                map.on('mouseleave', 'streets-line', () => {{ map.getCanvas().style.cursor = ''; }});

                map.fitBounds([[meta.bounds[0], meta.bounds[1]], [meta.bounds[2], meta.bounds[3]]], {{ padding: 50 }});

            }} catch (err) {{
                document.getElementById('loading').textContent = 'Error: ' + err.message;
                console.error(err);
            }}

            fetch('pois.geojson')
                .then(r => r.json())
                .then(poiData => {{
                    map.addSource('pois', {{ type: 'geojson', data: poiData }});
                    map.addLayer({{
                        id: 'poi-markers',
                        type: 'circle',
                        source: 'pois',
                        layout: {{ 'visibility': 'none' }},
                        paint: {{
                            'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 5, 18, 8],
                            'circle-color': '#9b27b0',
                            'circle-stroke-color': '#fff',
                            'circle-stroke-width': 1.5
                        }}
                    }});
                    document.getElementById('toggle-pois').addEventListener('change', (e) => {{
                        map.setLayoutProperty('poi-markers', 'visibility', e.target.checked ? 'visible' : 'none');
                    }});
                }})
                .catch(err => console.log('No POI data'));
        }});
    </script>
</body>
</html>'''


def write_binary_streets_output(output_dir: Path, segment_scores: dict, pois,
                                bbox: BBox, config: Config) -> None:
    """Write binary format output for streets mode."""
    output_dir.mkdir(parents=True, exist_ok=True)

    all_segments = []
    all_scores = []
    for edge_key, segments in segment_scores.items():
        for seg in segments:
            all_segments.append([
                seg["start"][0], seg["start"][1],
                seg["end"][0], seg["end"][1],
                seg["score"]
            ])
            all_scores.append(seg["score"])

    all_scores = np.array(all_scores)
    segment_data = np.array(all_segments, dtype=np.float32)

    streets_metadata = {
        "version": 1,
        "mode": "streets",
        "bounds": [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat],
        "segments": {
            "count": len(all_segments),
            "file": "segments.bin",
            "dtype": "float32",
            "fields": ["start_lon", "start_lat", "end_lon", "end_lat", "score"]
        },
        "scores": {
            "min": float(all_scores.min()) if len(all_scores) > 0 else 0,
            "max": float(all_scores.max()) if len(all_scores) > 0 else 0,
            "mean": float(all_scores.mean()) if len(all_scores) > 0 else 0
        },
        "tile_url": config.tile_url
    }

    with open(output_dir / "streets.json", "w") as f:
        json.dump(streets_metadata, f, indent=2)
    print(f"Wrote streets.json ({len(all_segments)} segments)")

    with open(output_dir / "segments.bin", "wb") as f:
        f.write(segment_data.tobytes())

    segments_size = segment_data.nbytes
    print(f"Wrote segments.bin ({segments_size / 1024:.1f} KB)")

    html = generate_binary_streets_viewer_html(config.tile_url, bbox)
    with open(output_dir / "index.html", "w") as f:
        f.write(html)
    print("Wrote index.html (binary streets viewer)")

    from indexer import SpatialIndex
    dummy_index = type('obj', (object,), {'pois': pois})()
    poi_geojson = generate_poi_geojson(dummy_index)
    with open(output_dir / "pois.geojson", "w") as f:
        json.dump(poi_geojson, f)
    print(f"Wrote {len(poi_geojson['features'])} POIs to pois.geojson")

    metadata = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": "streets",
        "bbox": bbox.to_tuple(),
        "config": config.to_dict(),
        "stats": {
            "n_pois": len(pois),
            "n_segments": len(all_segments),
            "n_segments_with_score": int((all_scores > 0).sum()) if len(all_scores) > 0 else 0,
            "score_min": float(all_scores.min()) if len(all_scores) > 0 else 0,
            "score_max": float(all_scores.max()) if len(all_scores) > 0 else 0,
            "score_mean": float(all_scores.mean()) if len(all_scores) > 0 else 0,
        }
    }
    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print("Wrote metadata.json")

    print(f"\nOutput written to {output_dir}/")
    print(f"To view: cd {output_dir} && python -m http.server 8000")


def write_streets_output(output_dir: Path, segment_scores: dict, pois,
                         bbox: BBox, config: Config, output_format: str = "geojson") -> None:
    """Write streets mode output files."""
    if output_format == "binary":
        write_binary_streets_output(output_dir, segment_scores, pois, bbox, config)
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    scores_display = normalize_segment_scores(segment_scores, "log1p")

    streets_geojson = generate_streets_geojson(segment_scores, scores_display)
    with open(output_dir / "streets.geojson", "w") as f:
        json.dump(streets_geojson, f)
    print(f"Wrote {len(streets_geojson['features'])} street segments to streets.geojson")

    from indexer import SpatialIndex
    dummy_index = type('obj', (object,), {'pois': pois})()
    poi_geojson = generate_poi_geojson(dummy_index)
    with open(output_dir / "pois.geojson", "w") as f:
        json.dump(poi_geojson, f)
    print(f"Wrote {len(poi_geojson['features'])} POIs to pois.geojson")

    all_scores = []
    for segments in segment_scores.values():
        for seg in segments:
            all_scores.append(seg["score"])
    all_scores = np.array(all_scores)

    metadata = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": "streets",
        "bbox": bbox.to_tuple(),
        "config": config.to_dict(),
        "stats": {
            "n_pois": len(pois),
            "n_segments": len(all_scores),
            "n_segments_with_score": int((all_scores > 0).sum()),
            "score_min": float(all_scores.min()) if len(all_scores) > 0 else 0,
            "score_max": float(all_scores.max()) if len(all_scores) > 0 else 0,
            "score_mean": float(all_scores.mean()) if len(all_scores) > 0 else 0,
        }
    }
    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print("Wrote metadata.json")

    html = generate_streets_viewer_html(config.tile_url, bbox)
    with open(output_dir / "index.html", "w") as f:
        f.write(html)
    print("Wrote index.html")

    print(f"\nOutput written to {output_dir}/")
    print(f"To view: cd {output_dir} && python -m http.server 8000")


def generate_binary_viewer_html(tile_url: str, bbox: BBox) -> str:
    """Generate HTML viewer that loads binary format data."""
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
        #controls {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 10px 15px;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            font-family: sans-serif;
            font-size: 12px;
        }}
        #controls label {{ cursor: pointer; }}
        .poi-popup {{ font-family: sans-serif; font-size: 12px; }}
        .poi-popup b {{ color: #333; }}
        #loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            padding: 20px 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            font-family: sans-serif;
            z-index: 1000;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="loading">Loading data...</div>
    <div id="info">
        <h3>Friendliness Index</h3>
        <p id="hover-info">Click on map for score details</p>
        <p id="stats"></p>
    </div>
    <div id="controls">
        <label><input type="checkbox" id="toggle-pois"> Show POIs</label>
        <label style="margin-left: 15px;"><input type="checkbox" id="toggle-graph"> Show Walk Graph</label>
    </div>
    <div id="legend">
        <h4>Friendliness</h4>
        <div class="legend-scale" id="gradient"></div>
        <div class="legend-labels"><span>Low</span><span>High</span></div>
    </div>
    <script src="https://unpkg.com/maplibre-gl@4.0.0/dist/maplibre-gl.js"></script>
    <script>
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

        async function loadBinaryData() {{
            const meta = await fetch('grid.json').then(r => r.json());
            const buffer = await fetch('scores.bin').then(r => r.arrayBuffer());
            const scores = new Float32Array(buffer);
            return {{ meta, scores }};
        }}

        function generateFeatures(meta, scores) {{
            const [minLon, minLat, maxLon, maxLat] = meta.bounds;
            const cellWidth = (maxLon - minLon) / meta.grid.cols;
            const cellHeight = (maxLat - minLat) / meta.grid.rows;
            const logMax = Math.log1p(meta.scores.max);

            const features = [];
            for (let row = 0; row < meta.grid.rows; row++) {{
                for (let col = 0; col < meta.grid.cols; col++) {{
                    const idx = row * meta.grid.cols + col;
                    const score = scores[idx];
                    const lon = minLon + col * cellWidth;
                    const lat = minLat + row * cellHeight;
                    const normalized = logMax > 0 ? Math.log1p(score) / logMax : 0;

                    features.push({{
                        type: 'Feature',
                        geometry: {{
                            type: 'Polygon',
                            coordinates: [[
                                [lon, lat],
                                [lon + cellWidth, lat],
                                [lon + cellWidth, lat + cellHeight],
                                [lon, lat + cellHeight],
                                [lon, lat]
                            ]]
                        }},
                        properties: {{ score, score_display: normalized }}
                    }});
                }}
            }}
            return {{ type: 'FeatureCollection', features }};
        }}

        map.on('load', async function() {{
            try {{
                const {{ meta, scores }} = await loadBinaryData();
                document.getElementById('loading').style.display = 'none';

                document.getElementById('stats').innerHTML =
                    `Range: ${{meta.scores.min.toFixed(1)}} - ${{meta.scores.max.toFixed(1)}}<br>` +
                    `Grid: ${{meta.grid.cols}} x ${{meta.grid.rows}} (${{meta.scores.count.toLocaleString()}} cells)`;

                console.time('generateFeatures');
                const geojson = generateFeatures(meta, scores);
                console.timeEnd('generateFeatures');

                map.addSource('scores', {{
                    type: 'geojson',
                    data: geojson
                }});

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

                map.on('click', 'score-fill', (e) => {{
                    if (e.features.length > 0) {{
                        const props = e.features[0].properties;
                        document.getElementById('hover-info').innerHTML =
                            `<b>Score:</b> ${{props.score.toFixed(2)}}<br>` +
                            `<b>Normalized:</b> ${{(props.score_display * 100).toFixed(1)}}%`;
                    }}
                }});

                map.on('mouseenter', 'score-fill', () => {{
                    map.getCanvas().style.cursor = 'pointer';
                }});
                map.on('mouseleave', 'score-fill', () => {{
                    map.getCanvas().style.cursor = '';
                }});

                map.fitBounds([[meta.bounds[0], meta.bounds[1]], [meta.bounds[2], meta.bounds[3]]], {{ padding: 50 }});

            }} catch (err) {{
                document.getElementById('loading').textContent = 'Error loading data: ' + err.message;
                console.error(err);
            }}

            fetch('pois.geojson')
                .then(response => response.json())
                .then(poiData => {{
                    map.addSource('pois', {{
                        type: 'geojson',
                        data: poiData
                    }});

                    map.addLayer({{
                        id: 'poi-named',
                        type: 'circle',
                        source: 'pois',
                        filter: ['has', 'name'],
                        layout: {{ 'visibility': 'none' }},
                        paint: {{
                            'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 5, 18, 9],
                            'circle-color': '#9b27b0',
                            'circle-stroke-color': '#fff',
                            'circle-stroke-width': 1.5,
                            'circle-opacity': 0.9
                        }}
                    }});

                    map.addLayer({{
                        id: 'poi-unnamed',
                        type: 'circle',
                        source: 'pois',
                        filter: ['!', ['has', 'name']],
                        layout: {{ 'visibility': 'none' }},
                        paint: {{
                            'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 3, 18, 6],
                            'circle-color': 'transparent',
                            'circle-stroke-color': '#ff9800',
                            'circle-stroke-width': 2,
                            'circle-opacity': 0.8
                        }}
                    }});

                    const poiClickHandler = (e) => {{
                        if (e.features.length > 0) {{
                            const props = e.features[0].properties;
                            const coords = e.features[0].geometry.coordinates;
                            let html = '<div class="poi-popup">';
                            html += props.name ? `<b>${{props.name}}</b><br>` : '<b style="color:#ff9800">(unnamed)</b><br>';
                            html += `<b>Type:</b> ${{props.type}}<br>`;
                            html += '</div>';
                            new maplibregl.Popup().setLngLat(coords).setHTML(html).addTo(map);
                        }}
                    }};
                    map.on('click', 'poi-named', poiClickHandler);
                    map.on('click', 'poi-unnamed', poiClickHandler);

                    document.getElementById('toggle-pois').addEventListener('change', (e) => {{
                        const vis = e.target.checked ? 'visible' : 'none';
                        map.setLayoutProperty('poi-named', 'visibility', vis);
                        map.setLayoutProperty('poi-unnamed', 'visibility', vis);
                    }});
                }})
                .catch(err => console.log('No POI data available'));

            fetch('graph.geojson')
                .then(response => response.json())
                .then(graphData => {{
                    map.addSource('graph', {{ type: 'geojson', data: graphData }});
                    map.addLayer({{
                        id: 'graph-edges',
                        type: 'line',
                        source: 'graph',
                        layout: {{ 'visibility': 'none' }},
                        paint: {{ 'line-color': '#666', 'line-width': 1, 'line-opacity': 0.6 }}
                    }}, 'score-fill');
                    document.getElementById('toggle-graph').addEventListener('change', (e) => {{
                        map.setLayoutProperty('graph-edges', 'visibility', e.target.checked ? 'visible' : 'none');
                    }});
                }})
                .catch(err => console.log('No graph data available'));
        }});
    </script>
</body>
</html>'''


def write_binary_grid_output(output_dir: Path, index: SpatialIndex,
                             scores: np.ndarray, bbox: BBox,
                             config: Config) -> None:
    """Write binary format output for grid mode."""
    n_points = len(index.grid_wgs)
    spacing = index.grid_spacing
    cols = index.grid_cols
    rows = index.grid_rows

    if cols * rows != n_points:
        print(f"Warning: grid dimensions {cols}x{rows}={cols*rows} != actual {n_points} points")

    utm_zone = int(index.utm_crs.split(":")[1])
    hemisphere = "N" if utm_zone < 32700 else "S"
    if hemisphere == "S":
        utm_zone -= 32700
    else:
        utm_zone -= 32600

    grid_metadata = {
        "version": 1,
        "mode": "grid",
        "bounds": [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat],
        "grid": {
            "spacing_m": spacing,
            "cols": cols,
            "rows": rows,
            "utm_zone": utm_zone,
            "utm_hemisphere": hemisphere
        },
        "scores": {
            "count": n_points,
            "min": float(scores.min()),
            "max": float(scores.max()),
            "mean": float(scores.mean()),
            "file": "scores.bin",
            "dtype": "float32"
        },
        "tile_url": config.tile_url
    }

    with open(output_dir / "grid.json", "w") as f:
        json.dump(grid_metadata, f, indent=2)
    print(f"Wrote grid.json ({cols}x{rows} = {cols*rows} cells)")

    scores_f32 = scores.astype(np.float32)
    with open(output_dir / "scores.bin", "wb") as f:
        f.write(scores_f32.tobytes())

    scores_size = scores_f32.nbytes
    print(f"Wrote scores.bin ({scores_size / 1024:.1f} KB)")

    html = generate_binary_viewer_html(config.tile_url, bbox)
    with open(output_dir / "index.html", "w") as f:
        f.write(html)
    print("Wrote index.html (binary viewer)")


def write_output(output_dir: Path, index: SpatialIndex, scores: np.ndarray,
                 scores_display: np.ndarray, bbox: BBox, config: Config,
                 graph=None, output_format: str = "geojson") -> None:
    """Write all output files.

    Args:
        graph: Optional networkx graph to export as graph.geojson
        output_format: "geojson" or "binary"
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_format == "binary":
        write_binary_grid_output(output_dir, index, scores, bbox, config)
    else:
        geojson = generate_geojson(index, scores, scores_display)
        with open(output_dir / "results.geojson", "w") as f:
            json.dump(geojson, f)
        print(f"Wrote {len(geojson['features'])} features to results.geojson")

        html = generate_viewer_html(config.tile_url, bbox, index.grid_spacing)
        with open(output_dir / "index.html", "w") as f:
            f.write(html)
        print("Wrote index.html")

    poi_geojson = generate_poi_geojson(index)
    with open(output_dir / "pois.geojson", "w") as f:
        json.dump(poi_geojson, f)
    print(f"Wrote {len(poi_geojson['features'])} POIs to pois.geojson")

    if graph is not None:
        graph_geojson = generate_graph_geojson(graph)
        with open(output_dir / "graph.geojson", "w") as f:
            json.dump(graph_geojson, f)
        print(f"Wrote {len(graph_geojson['features'])} edges to graph.geojson")

    metadata = generate_metadata(bbox, config, len(index.pois), len(index.grid_wgs), scores)
    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print("Wrote metadata.json")

    print(f"\nOutput written to {output_dir}/")
    print(f"To view: cd {output_dir} && python -m http.server 8000")
