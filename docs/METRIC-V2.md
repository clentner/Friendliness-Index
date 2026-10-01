# Boston front doors v2

This opt-in pilot is separate from the unchanged legacy `generate.py` pipeline.
It deliberately changes scores; do not compare colors to legacy output as though
only the renderer changed. The product has no adjustable scoring controls.

## Definition

For grid location q and every permitted OSM POI p, snap each to its nearest
densified pedestrian graph node, using EPSG:32619 Euclidean meters. Both snap
connectors must be at most 75 m. Let d be query connector + undirected shortest
network path + POI connector. Sum exp(-d/120) over individual POIs with d <= 800 m.
POIs sharing a node still contribute separately. Distinct OSM objects are distinct
POIs; identifying duplicate real-world businesses represented by several objects
is a future data-cleaning task. No intersection penalty is applied.

The 25 m grid uses a fixed absolute UTM lattice. Grid cell (i,j) covers the
half-open interval origin + (25i,25j) to origin + (25(i+1),25(j+1)); its score
location is the center. Raster pixels sample these cells after proper inverse
projection; they never reconstruct a latitude/longitude grid.

Graph nodes preserve OSM IDs, including distinct IDs at coincident coordinates.
Adjacent way-node segments preserve bends and explicit junctions. Subdivision to
at most 25 m avoids long-edge endpoint snapping. Parallel copies of the same
node pair use the shortest edge rather than summing duplicate weights. All
components remain. Exact snap ties resolve by stable graph order; spatial
subsets preserve this order.

## Access and location proxies

`poi_config.json` retains the project's editorial category allow/deny lists.
The importer recognizes ordinary pedestrian-compatible highway classes and
explicit foot permission. `foot=no/private/use_sidepath` and `access=no/private`
are excluded unless explicit positive foot permission overrides general access.
Impassable returned barrier nodes remove adjacent edges. This is not a complete
pedestrian router: conditional restrictions, opening hours, turn restrictions,
elevators, level changes and barrier geometry require further work. The graph is
undirected even for one-way road traffic.

Node POIs use their coordinates. Way POIs use a projected representative point;
relation POIs use Overpass's bounds center to keep input bounded. These locations
stand in for entrances. A straight snap connector can cross a wall/water boundary;
75 m bounds that approximation but does not make it barrier-aware. Relation
centers and area POIs can be outside practical entrances or too far from a road.
Missing POIs and map coverage are not evidence of unfriendly or unsafe streets.

## Boundaries and no-data

Every query belongs to exactly one absolute projected chunk (default 2,000 m).
Each chunk sees a 975 m halo: 800 m radius + two 75 m snap allowances + one 25 m
graph segment. Edges are straight metric segments, so network path distance is
never less than projected displacement. The conservative halo therefore retains
all contributing paths and snap candidates for interior queries. Source
acquisition adds another grid cell of padding. Source coverage and SHA-256 are
checked before scoring; partial Overpass responses are rejected.

Source completeness is still an assumption: Overpass bbox way selection can
omit an unusually long original segment crossing the acquisition rectangle when
all its original nodes are outside. The halo substantially reduces this risk
for the central-city pilot, but does not prove completeness. A future larger
PBF source importer should retain every intersecting segment explicitly. Saved
acquisition category provenance is checked so expanding the allow-list cannot
silently reuse an extract that never requested those POIs.

Chunking does not mean the entire input is streamed: the bounded source graph is
resident, and each chunk constructs a smaller sparse graph. The pilot is capped
at 250 MiB source JSON, 1,000,000 graph nodes, 20,000 POIs, 200,000 grid cells and 400
finest-level raster tiles. The search deadline is checked between Dijkstra runs.
The source and graph caps were raised for the authorized three-city expansion;
the score, projection, halo and rendering algorithms are unchanged. That laptop
build also used an external 15-minute wall-clock / 1.5-GiB working-set monitor.
Large regions require independently acquired bounded source shards; this pilot
does not download or compute an entire state automatically.

NaN means no walking-network snap within 75 m. Zero means a valid snap but no
qualifying POIs. Outside requested geographic coverage is also transparent in
the renderer, and a coverage outline explains the boundary.

## Display and provenance

The fixed display value is clamp(log1p(score)/log1p(30),0,1). Scores >=30 saturate
the palette, but original float32 values remain available. Display normalization
never depends on a tile or regional maximum. Raster overview levels are
premultiplied-alpha-aware image resampling for display, not analytic averaged
scores. Zoom 14 is the native raster level; closer zooms overzoom those pixels.

Builds record source timestamp/checksum/query, metric version, parameter values,
code hash, POI-filter hash and score hash. Changing semantics requires a metric
version bump; dataset IDs also incorporate implementation and content hashes.
Legacy scoring/output files are untouched.

## Tests

`python -m unittest discover -s tests -v` includes independent forward shortest-path
comparison, multiplicity, connectors/cutoff, coincident identity, disconnected
components, curved ways, duplicate ways, tile projection and chunk seams.
`python -m scripts.benchmark` checks a larger synthetic lattice against a global
reference. Real-data seam samples are checked by `scripts/real-seams.py`.
