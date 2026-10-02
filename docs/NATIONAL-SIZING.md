# National storage and file-count planning

These are planning scenarios, not measurements of a national build or a hosting
quote. Massachusetts dataset `5124e42eb1483a75` is the measured calibration.
The estimates retain the 25 m analytical cells, 256-pixel PNG tiles through zoom
14, fixed scoring/color rules, sparse omission of empty tiles, and downloadable
float32 scores. They exclude source PBFs, SQLite indexes, checkpoints, duplicate
releases, backups, and the third-party basemap. GB below means decimal GB.

## Measured Massachusetts baseline

| Component | Files | Bytes |
| --- | ---: | ---: |
| PNG score pyramid, zooms 7–14 | 9,478 | 147,227,322 |
| Exact float32 blocks, at most 320 × 320 cells each | 426 | 174,044,160 |
| Viewer, metadata, boundary and transparent fallback | 12 | About 1.63 million |
| Complete hosted build | 9,916 | About 322.9 million |

The 6,893 finest-zoom tiles occupy 39.3% of the state's enclosing tile rectangle;
46.7% of their pixels are nontransparent. Every published PNG has a distinct
SHA-256, so exact-payload deduplication offers no saving for this build. Zoom 14
accounts for 72.7% of image file count but only 15.9% of image bytes. Its median
PNG is 2,062 bytes, whereas zoom 13's median is 39,044.5 bytes. File count and
storage therefore cannot be extrapolated with one common density multiplier.

Individually gzip-compressing all exact raw blocks at level 6 yielded 27,041,001
bytes in a trial, versus 174,044,160 bytes uncompressed: an 84.5% saving with no
loss of values. This trial did not change the published raw format. The full
unpartitioned analytical rectangle is 366,134,460 bytes, including empty marine
areas, and is not an extra hosted download.

## Explicit scenario assumptions

The [FHWA 2023 public-road table](https://www.fhwa.dot.gov/policyinformation/statistics/2023/hm20.cfm)
reports 36,894 miles in Massachusetts and 4,199,209 in the 50 states plus DC.
Subtracting Alaska's 17,639 and Hawaii's 4,522 gives a lower-48-plus-DC ratio of
113.2 to Massachusetts. Public roads are a coverage proxy, not our actual OSM
walking graph: they omit many paths and include non-walkable roads.

As an independent density check, 2020 Census populations imply approximately
46.8 Massachusetts populations in the lower 48 plus DC, or 47.1 in all 50 plus
DC. Sources: [Massachusetts](https://www.census.gov/quickfacts/massachusetts),
[United States](https://www.census.gov/quickfacts/US),
[Alaska](https://www.census.gov/quickfacts/fact/table/AK/PST045224), and
[Hawaii](https://www.census.gov/quickfacts/fact/table/HI/PST045224).
The gap between population and road ratios is why scaling only by land area,
population, or Massachusetts's mean PNG size would be misleading.

For image file count, a sensitivity band of 0.75–2.0 times the road-ratio
extrapolation gives roughly 0.8–2.2 million lower-48 tiles. This coefficient is
an explicit engineering assumption, allowing different road dispersion, OSM
mapping, and latitude-dependent tile footprints; it is not statistically fitted.
Sparse rural tiles can be numerous while compressing well. A broad 5–25 GB image
range brackets population- and road-scaled image bytes with that uncertainty.

For raw storage, assume 50,000–125,000 occupied 8 km × 8 km analytical blocks.
Each full uncompressed block is 409,600 bytes, giving 20.5–51.2 GB. These blocks
are saved whenever any cell is reachable, including zero scores far from a POI;
a lone rural road can therefore retain an otherwise empty block. This is a
coverage/packing assumption to validate with rural samples, not a national
occupied-block count. It explains why raw bytes may dominate the hosted total.

| Coverage | Loose hosted files | PNG imagery | Uncompressed exact raw blocks | Total planning range |
| --- | ---: | ---: | ---: | ---: |
| Lower 48 plus DC | About 0.9–2.4 million | 5–25 GB | 20–51 GB | About 25–80 GB |
| All 50 plus DC | About 1–3 million | 6–30 GB | 21–55 GB | About 30–90 GB |

The all-50 range includes extra allowance for Alaska's high-latitude tile
footprints and scattered settlements. It does not fill Alaska's uninhabited
area or the ocean between states. Territories are excluded. Both ranges are
roughly one-to-three-million-file, tens-of-GB estimates; they are not proven
upper bounds. Applying the Massachusetts raw gzip ratio would reduce the raw
component greatly, but national entropy and a compatible indexed compressed
format must be measured before committing to a compressed total.

The cheapest next validation is several bounded samples covering a dense city,
Midwest road grid, sparse western region, Alaska, and Hawaii, measuring occupied
tiles, raw-block occupancy, PNG bytes and lossless raw compression separately.
National preprocessing also needs appropriate regional metric projections,
cross-region seam tests, and Canadian/Mexican border context where relevant.
The Massachusetts EPSG:32619 grid must not simply be stretched across the US.

## Fewer files with the same information

Raster [PMTiles works with MapLibre](https://docs.protomaps.com/pmtiles/maplibre).
It can place the same PNG payloads in indexed archives and fetch only the byte
ranges needed for the current view. This changes delivery, not the score metric,
tile resolution, or image quality. One archive could hold the Massachusetts
imagery; a national release could use a manageable set of regional archives.
The exact float32 download needs its own indexed, losslessly compressed format;
it cannot be replaced by the display PNGs without losing analytical precision.

An archive primarily solves object count. The PNGs are already compressed, and
this MA build has no duplicate PNG payloads. Avoid promising a major PNG byte
reduction from packaging alone. A single ZIP is useful for a full download but
does not by itself implement selective in-browser map loading.

Cloudflare Pages Free permits
[20,000 files and 25 MiB per asset](https://developers.cloudflare.com/pages/platform/limits/).
It currently answers [HTTP range requests with 200 rather than 206](https://developers.cloudflare.com/pages/configuration/serving-pages/).
Thus uploading a large PMTiles file to Pages is not a complete solution. A
range-capable object host, delivery/cache design, request-cost assessment and
client integration are still needed. No storage service was created or paid
plan enabled for this work. Massachusetts already fits the existing static
limits; national delivery should be designed before a national export is run.
