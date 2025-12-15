# Friendliness Index
A way to visualize the friendliest places to walk.

Generates a heatmap, e.g. greater Boston area:

![A walkability heatmap of the Boston metro area](boston.png)

## Procedure
1. From OpenStreetMap data, generate a connected graph of all walkable ways (sidewalks, paths, etc).
1. From OpenStreetMap data, extract a list of "friendly" POIs (shops etc)
1. Snap a rectangular grid to the walk graph. Snap the POIs to the walk graph.
    - There is a maximum snap distance to prevent calculating "walk" scores from within bodies of water etc
1. For each point on the grid, run Dijkstra along the walk graph to nearby POIs. Compute a weighted sum using exponential decay for greater walk distances.


## Usage
1. Clone repo and set up the virtualenv
1. Download a PBF file containing the OSM data for your area
1. Pick out a bounding box. Allow a few hundred extra meters on all sides so that edges of the grid can have the same number of neighbors as the center.
1. Run the script:

```
python3 generate.py \
  --pbf massachusetts-251213.osm.pbf \                 # Input file e.g. from Geofabrik
  --bbox="-71.323487,42.184944,-70.921937,42.522139" \ # Bounding box
  --lambda 120 \                                       # Exponential decay parameter, shorter=faster decay
  --rmax 800 \                                         # Max influence radius
  --ntarget 250000 \                                   # Target # of grid points
  --out output_large                                   # Output directory
```

## Authorship
Written using Claude Code. See `spec.txt` for the initial prompt and `spec_alterations.txt`
for improvements discovered during implementation.
