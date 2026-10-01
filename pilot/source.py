"""Bounded OSM input and provenance for the Boston pilot."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union
from pilot.metric import HALO, SPACING, make_graph

TO_METERS = Transformer.from_crs(4326, 32619, always_xy=True)
TO_WGS = Transformer.from_crs(32619, 4326, always_xy=True)
MAX_DOWNLOAD = 50 * 1024 * 1024
WALKABLE = {"residential", "living_street", "unclassified", "service", "pedestrian",
            "footway", "path", "steps", "track", "corridor", "cycleway", "bridleway",
            "tertiary", "tertiary_link", "secondary", "secondary_link", "primary", "primary_link"}


def projected_bounds(bbox):
    west, south, east, north = bbox
    if not (-72 <= west < east <= -70 and 41 <= south < north <= 43.5):
        raise ValueError("Pilot supports Greater Boston only; expected lon,lat,lon,lat")
    # Sample all four edges to avoid corner-only projected bounding boxes.
    t = np.linspace(0, 1, 65)
    lon = np.r_[west+(east-west)*t, west+(east-west)*t, np.full(65, west), np.full(65, east)]
    lat = np.r_[np.full(65, south), np.full(65, north), south+(north-south)*t, south+(north-south)*t]
    x, y = TO_METERS.transform(lon, lat)
    return np.array([min(x), min(y), max(x), max(y)])


def acquisition_bounds(bbox):
    bounds = projected_bounds(bbox) + np.array([-HALO-SPACING, -HALO-SPACING, HALO+SPACING, HALO+SPACING])
    x0, y0, x1, y1 = bounds
    t = np.linspace(0, 1, 65)
    x = np.r_[x0+(x1-x0)*t, x0+(x1-x0)*t, np.full(65,x0), np.full(65,x1)]
    y = np.r_[np.full(65,y0), np.full(65,y1), y0+(y1-y0)*t, y0+(y1-y0)*t]
    lon, lat = TO_WGS.transform(x,y)
    return [min(lon), min(lat), max(lon), max(lat)]


def download(bbox, destination):
    bounds = projected_bounds(bbox)
    if (bounds[2]-bounds[0]) * (bounds[3]-bounds[1]) > 120e6:
        raise ValueError("Download core limited to 120 km²")
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError("Source already exists; reuse it or choose a new path")
    west, south, east, north = acquisition_bounds(bbox)
    extent = f"{south},{west},{north},{east}"
    config = json.loads(Path("poi_config.json").read_text(encoding="utf-8"))
    filters = []
    for tag, values in config["allow"].items():
        filters.append(f'["{tag}"]' if values == ["*"] else
                       f'["{tag}"~"^({"|".join(values)})$"]')
    # Avoid transporting full geometries of enormous POI relations. Their
    # bounds-center is an explicit v2 location proxy, not a claimed entrance.
    points_ways = "".join(f'{kind}{f}({extent});' for f in filters for kind in ["node","way"])
    relations = "".join(f'relation{f}({extent});' for f in filters)
    query = (f'[out:json][timeout:90][maxsize:268435456];'
             f'(way["highway"]({extent});node["barrier"]({extent});{points_ways});out body geom;'
             f'({relations});out center;')
    request = Request("https://overpass-api.de/api/interpreter",
                      data=urlencode({"data":query}).encode(),
                      headers={"User-Agent":"FriendlinessIndexPilot/2 (bounded research extract)"})
    with urlopen(request, timeout=120) as response:
        raw = response.read(MAX_DOWNLOAD + 1)
    if len(raw) > MAX_DOWNLOAD:
        raise ValueError("Source exceeds 50 MiB download cap")
    data = json.loads(raw)
    if "remark" in data or not data.get("elements"):
        raise ValueError(f"Incomplete Overpass response: {data.get('remark', 'empty')}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    metadata = {"source":"https://overpass-api.de/api/interpreter", "query":query,
                "coverage_bbox":[west,south,east,north], "core_bbox":bbox,
                "downloaded_at":datetime.now(timezone.utc).isoformat(),
                "osm_timestamp":data.get("osm3s",{}).get("timestamp_osm_base"),
                "sha256":hashlib.sha256(raw).hexdigest(), "bytes":len(raw),
                "license":"ODbL-1.0", "attribution":"© OpenStreetMap contributors"}
    destination.with_suffix(destination.suffix+".meta.json").write_text(json.dumps(metadata,indent=2), encoding="utf-8")
    return metadata


def permitted(tags):
    foot = tags.get("foot", "")
    return foot in {"yes","designated","permissive"} or (
        foot not in {"no","private","use_sidepath"} and tags.get("access") not in {"no","private"})


def walking(tags):
    return permitted(tags) and (tags.get("highway") in WALKABLE or
                               (tags.get("highway") and tags.get("foot") in {"yes","designated","permissive"}))


def allowed_poi(tags, config):
    return (any(tag in tags and ("*" in values or tags[tag] in values)
                for tag, values in config["allow"].items()) and
            not any(tags.get(tag) in values for tag, values in config["deny"].items()))


def representative(element):
    if element["type"] == "node":
        return TO_METERS.transform(element["lon"], element["lat"])
    if element["type"] == "relation" and "center" in element:
        return TO_METERS.transform(element["center"]["lon"], element["center"]["lat"])
    if element["type"] == "way":
        geometries = [element.get("geometry", [])]
    else:
        geometries = [m.get("geometry",[]) for m in element.get("members",[])
                      if m.get("role") != "inner"]
    lines = []
    for geometry in geometries:
        points = [TO_METERS.transform(p["lon"],p["lat"]) for p in geometry if p and "lon" in p]
        if len(points) >= 2:
            lines.append(LineString(points))
    if not lines:
        return None
    polygons = list(polygonize(unary_union(lines)))
    geometry = unary_union(polygons) if polygons else unary_union(lines)
    point = geometry.representative_point()
    return point.x, point.y


def load(path, bbox, config_path="poi_config.json"):
    path = Path(path)
    if path.stat().st_size > MAX_DOWNLOAD:
        raise ValueError("Source exceeds pilot 50 MiB limit")
    provenance = json.loads(path.with_suffix(path.suffix+".meta.json").read_text(encoding="utf-8"))
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != provenance["sha256"]:
        raise ValueError("Source checksum mismatch")
    coverage, required = provenance["coverage_bbox"], acquisition_bounds(bbox)
    if any(required[i] < coverage[i]-1e-9 for i in [0,1]) or any(required[i] > coverage[i]+1e-9 for i in [2,3]):
        raise ValueError("Source coverage lacks the required halo; acquire a larger extract")
    data = json.loads(raw)
    if "remark" in data:
        raise ValueError("Partial OSM response rejected")
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    nodes, ways, pois, seen = {}, [], [], set()
    blocked = {e["id"] for e in data["elements"] if e["type"] == "node" and not permitted(e.get("tags",{}))}
    missing = 0
    for element in data["elements"]:
        identity = (element["type"],element["id"])
        if identity in seen:
            continue
        seen.add(identity)
        tags = element.get("tags",{})
        if element["type"] == "way" and walking(tags):
            refs, geometry = element.get("nodes",[]), element.get("geometry",[])
            if len(refs) != len(geometry) or any(not p for p in geometry):
                missing += 1
                continue
            for ref, p in zip(refs,geometry):
                nodes[ref] = TO_METERS.transform(p["lon"],p["lat"])
            # Remove impassable nodes without connecting across the resulting gap.
            for a,b in zip(refs,refs[1:]):
                if a not in blocked and b not in blocked:
                    ways.append([a,b])
        if allowed_poi(tags,config) and permitted(tags):
            point = representative(element)
            if point is not None:
                pois.append(point)
    if missing:
        raise ValueError(f"{missing} walking ways lack complete geometry")
    graph = make_graph(nodes,ways)
    if len(graph.xy) > 300000 or len(pois) > 20000:
        raise ValueError("Input exceeds pilot graph/POI budget")
    return graph, np.asarray(pois).reshape(-1,2), provenance
