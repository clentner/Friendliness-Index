# Massachusetts expansion

This is a separate, unpublished regional build. The existing three-city Pages
deployment and its source checkout remain the rollback reference.

## Source and resource plan

The dated 2026-10-01 Geofabrik extracts for Massachusetts, Connecticut, Rhode
Island, New Hampshire, Vermont and New York total 1,194,524,182 bytes. Downloads
are streamed to partial files and checked against the provider's MD5 and a
recorded SHA-256. PBF replication timestamps must agree. A Massachusetts OSM
administrative-boundary query supplies the output mask, including islands.
The union of the six extract polygons must contain the output boundary buffered
by 1,025 m; incomplete context is a hard error. The extra 50 m beyond the 975 m
scoring halo conservatively covers grid and graph segment edges.

The boundary's enclosing EPSG:32619 grid contains 91,533,615 cells at 25 m,
requiring 366,134,460 bytes on disk. The 7,197 intersecting absolute 2 km jobs
each create at most 6,400 query coordinates. Only Massachusetts cell centers are
scored. Working-set and wall-clock budgets remain explicit; a monitor stops a
stage if system RAM headroom falls below 384 MiB.

## Architecture

`regional_source.py` streams PBFs through a disk location cache into SQLite.
Walking/access rules, POI proxies, graph identity, 25 m subdivision and fixed
scoring constants come from the pilot. Whole original segments are tested for
intersection; original endpoints need not be inside the retained region. A
global order key preserves snap tie-breaking across independently loaded halos.
Duplicate OSM identities across overlapping state extracts are retained once.
Relation POIs use the geographic bounds center, including nested members.
Unresolved relation geometry blocks export and must be investigated.

SQLite's spatial index loads one job's graph and POIs. Scoring uses the existing
`metric.score`, discards halo output, and writes an atomic per-job checkpoint
with a checksum. Input, configuration, code and boundary signatures prevent
mixing checkpoints from different builds. The score raster is assembled on disk
only after all jobs finish. Interrupted scoring can reuse verified checkpoints.
The importer commits every 10,000 walking ways and checkpoints completed source
files. After the old process exits, explicit `resume=True` verifies the input
identity and source hashes, skips completed files, and replays an incomplete
file idempotently. Derived spatial indexes are rebuilt if finalization was
interrupted. Every replay uses a fresh native location cache.

The full rectangular raster pyramid would contain 23,587 files, exceeding
Cloudflare Pages' Free-plan 20,000-file limit. Export writes only tiles with
nontransparent data, including the parent pyramid down to zoom 7 for statewide
phone-sized views. The manifest enumerates
published tiles, and the viewer resolves other requests to one transparent PNG.
This avoids expected 404s and false user-visible tile errors. Exact analytic
scores are partitioned into 320 x 320-cell blocks (at most 409,600 bytes each),
with checksums and a raw index. The raw index defines absent blocks as NaN.
Export checks **all** hosted assets against the 20,000-file and 25 MiB-per-file
limits before declaring completion.

The CRS remains EPSG:32619 even in western Massachusetts, preserving the existing
fixed metric's coordinate system. This expansion does not introduce a new local
projection or independently normalize colors. Source completeness and OSM's
existing access, entrance and barrier approximations still apply.

## Reproduce

Use the isolated Python 3.13 environment with `requirements-region.txt`. Vendor
the existing locked MapLibre assets using the repository's vendor command.

```powershell
python scripts/acquire_ma.py
python -c "from pilot.regional_source import index_sources; index_sources('data/ma-20261001', 'data/ma-20261001/source.sqlite')"
python -m pilot.region plan
python -m pilot.region score --sample
python scripts/region-seams.py
python -m pilot.region score
python scripts/audit-region-access.py
python -m pilot.region export
python scripts/verify-region.py
python -m unittest discover -s tests -v
node scripts/region-browser-qa.cjs
```

Browser QA uses the locked Playwright dependency and the installed Microsoft
Edge browser. A local preview can be served with
`python -m http.server 8765 --bind 127.0.0.1 --directory build/massachusetts`.

Run long stages through `scripts/monitor_stage.py` with explicit memory/time
limits and the actual interpreter executable (not the Windows venv launcher).
Pyosmium on Windows may retain mapping handles until the importer process exits;
the native location arrays are cleared between files and unique cache filenames
avoid collisions. Generated caches stay under ignored `data/`.
The New York pass exposed native read-ahead memory beyond the Python/SQLite
cache budget. The importer now defaults to two decompression threads and queue
sizes of two using the documented `OSMIUM_POOL_THREADS`,
`OSMIUM_MAX_INPUT_QUEUE_SIZE`, `OSMIUM_MAX_OSMDATA_QUEUE_SIZE` and
`OSMIUM_MAX_WORK_QUEUE_SIZE` process-local controls. Existing explicit environment
values are respected and recorded in source metadata; the external working-set
guard remains unchanged. See [libosmium runtime configuration](https://osmcode.org/libosmium/manual.html#run-time-configuration).
The six-source relation table contains 153,109 relations and 31,045,280 bytes of
member JSON. Only 1,526 are POI roots; loading their nested children requires
1,534 relations. Retaining only that reachable relation graph in Python removed
roughly 250 MiB at the same early New York processing stage. The full relation
table stays on disk. Walking graph vertices and POIs are retained only for the
Massachusetts support region; the whole-state native node-location cache is
temporary and is released after each extract.

The resource safeguards were exercised during the build: one import attempt
stopped at 1,800 seconds after 870,000 committed walking ways, and two subsequent
New York passes reached the 1,100 MiB working-set guard. Recovery, bounded native
read-ahead and selective relation loading address these measured failures. The
limits were not raised. Per-attempt resource logs and the one-time checkpoint
provenance migration record are retained under `qa-artifacts/`.

## Release gates

Dataset `5124e42eb1483a75` passed the full import, bounded scoring, independent
real-data seam/border comparisons, asset validation, and desktop/phone-sized
browser checks. Physical mobile and cellular testing remain separate from
desktop viewport simulation. No production deployment is part of this build.

## Measured source and representative checks

The completed source index contains 9,919,658 vertices, 10,368,853 edges and
50,785 POIs. Its six extracts share the timestamp `2026-10-01T20:22:06Z`.
Unresolved relation count and missing source-support area are both zero.
The final resumed import/finalization pass took 966.2 seconds and peaked at
1,073,680,384 bytes of working memory; prior interrupted attempts are additional
work, not included in that number. This is not a fresh-import timing benchmark.

Eight 2 km scoring jobs completed in 8.27 seconds total, with a monitored peak
working set of 165,560,320 bytes. Each job scores at most 6,400 cell centers.

| Location | Halo graph vertices | POIs | Job seconds |
| --- | ---: | ---: | ---: |
| Nantucket | 9,773 | 150 | 0.163 |
| Hyannis | 18,004 | 175 | 0.285 |
| Fall River | 19,006 | 132 | 0.267 |
| Springfield | 24,762 | 189 | 0.381 |
| Worcester | 50,748 | 654 | 1.740 |
| Boston | 53,298 | 1,808 | 4.030 |
| Pittsfield | 15,200 | 154 | 0.250 |
| Newburyport | 15,542 | 230 | 0.350 |

The eight-location independent forward-search oracle covers 96 reachable grid
cells. Its maximum absolute discrepancy from halo scoring is 1.60e-14. Separate
checks on 12 Massachusetts cells at each of the Connecticut and New Hampshire
borders prove nonzero contributions from destinations outside Massachusetts;
removing those destinations changes scores by up to 0.571 and 9.002 respectively.
The final 22-test regression suite and the strengthened real-data checks pass.
An additional acquisition/access audit scans all six PBFs for private nodes
selected by the legacy Overpass query but excluded by the editorial POI filter.
It found one candidate in Vermont and no matching retained graph nodes. Release
verification requires this audit to match the scoring-run signature and rejects
any affected retained node, so the legacy acquisition interaction cannot pass
unnoticed on another build.

Statewide scoring completed all 7,197 jobs (7,189 new and eight reused samples)
in 762.75 seconds, with 182,820,864 bytes peak working memory. The grid has
43,991,975 Massachusetts cell centers and 16,902,533 reachable cells. Of the jobs,
1,497 contain no reachable output. Median job time is 0.0634 seconds, p95 is
0.2589 seconds, and the slowest is 9.122 seconds. The largest loaded halo has
67,898 vertices and the largest POI set has 2,585 entries. There are 176,697
grouped reverse searches across the entire state. These observed maxima are
below the unchanged 150,000-node, 20,000-POI and 120-second per-job limits.

## Completed export and browser validation

The local site is `build/massachusetts`. Export took 794.20 seconds (795.11
seconds monitored) and peaked at 470,409,216 bytes of working memory. Its 9,916
hosted files total 322,907,478 bytes (322.9 MB); the largest is 1,048,625 bytes. The
site is below both static hosting limits. The verifier checked every PNG,
every exact-score block against the source memmap, all block checksums, the
full score checksum, missing blocks as NaN, the source-access audit signature,
and the exact set of published tile paths.

| Zoom | PNG files | Bytes |
| --- | ---: | ---: |
| 7 | 3 | 86,315 |
| 8 | 7 | 338,578 |
| 9 | 19 | 1,260,732 |
| 10 | 51 | 4,161,141 |
| 11 | 157 | 12,824,220 |
| 12 | 514 | 34,376,138 |
| 13 | 1,834 | 70,807,934 |
| 14 | 6,893 | 23,372,264 |
| Total imagery | 9,478 | 147,227,322 |

The 426 raw blocks add 174,044,160 bytes. The remaining 12 assets include the
viewer, vendored libraries, metadata, boundary, headers, and transparent PNG.
The manifest is 154,200 bytes; the exact-score index is 66,476 bytes.

Microsoft Edge headless passed at 1440 × 900 and 390 × 844. The checks visit
Boston, Worcester, Springfield, Pittsfield, North Adams, Lowell, Provincetown,
Nantucket and Vineyard Haven; verify loaded scores, full-state overview,
overlay toggle, return-home behavior, and no horizontal overflow; and exercise
transparent tiles both outside the state and with a forced-empty tile index.
There were no page errors or failed HTTP responses. Screenshot review caught
and fixed a mobile overview crop caused by the pilot's minimum map zoom. The
regional viewer now permits the fit needed to show the entire state below the
information panel, and QA checks both projected boundary corners.

Coverage labels use the actual boundary GeoJSON, including polygon holes and
separate islands, rather than the enclosing rectangle. The same geometry draws
the coverage outline. Checks alternate Hartford, Providence and Nashua (all
outside Massachusetts but inside its bounding box) with Nantucket, Vineyard
Haven and Cuttyhunk. Both viewport sizes classify all six correctly. Synthetic
hole, MultiPolygon island and boundary-point checks also pass. A failed boundary
fetch shows an error instead of falling back to an inaccurate rectangle.
Persistent panel padding keeps the camera's geographic center in the visible
map area, so initial overview and return-home labels remain correct on phones.
No scoring or colorization changed: reachable zero remains blue, while no-data
remains transparent. The existing tests for that distinction pass again.

| Measurement | Desktop viewport | Phone viewport |
| --- | ---: | ---: |
| Local initial load | 438 ms | 239 ms |
| Initial PNG requests | 20 | 3 |
| Pan/zoom operations | 100 | 100 |
| p95 animation frame interval | 16.8 ms | 16.8 ms |
| Long tasks during interaction | 0 | 0 |
| JS heap change after warmup | -15,504 bytes | 266,756 bytes |

A separate cold phone-sized run throttled to 1.5 Mbps and 150 ms latency took
8,768 ms and transferred 1,448,695 bytes. All these browser checks use loopback
with external basemap traffic excluded. They measure this computer's browser,
not phone hardware, real cellular routing, CDN compression, or total browser/GPU
resident memory. The heap measurements are post-GC JavaScript heap only.

The shared viewer also passed the existing pilot browser suite against a local
copy of dataset `43618671d5d41436`: both viewports, 100 pan/zoom operations each,
all existing performance gates, and the unavailable-manifest error scenario.
The original checkout and deployment were not modified.

The boundary-label correction changed only `app.js` in the exported site,
adding 1,542 bytes. File count, imagery, raw scores, dataset ID, scoring/export
timings, and resource measurements remain unchanged. The full analytical score
SHA-256 was rechecked after the correction; no long build was rerun.

The source import was the memory bottleneck; relation selection and native
read-ahead required fixes before it met the unchanged guard. Scoring remained
well below that memory ceiling. PNG export took slightly longer than scoring,
and a cold slow connection spends most of its load budget transferring the app
bundle and initial imagery. These measurements do not justify extrapolating
fresh national import time from the final resumed Massachusetts import.

Local evidence is retained in `qa-artifacts/region-verification.json`,
`region-seams.json`, `region-access-audit.json`, `scoring-summary.json`,
`region-unit-tests.txt`, per-stage resource logs, and `region-browser/` screenshots
and `results.json`. See [national sizing](NATIONAL-SIZING.md) for explicit
US file-count/storage scenarios and packaging options without changing scores.
The compact [validation record](ma-validation.json) preserves numerical results
in the repository; generated data and screenshots remain outside Git.

Sources: [Geofabrik Massachusetts](https://download.geofabrik.de/north-america/us/massachusetts.html),
[Pyosmium handlers](https://docs.osmcode.org/pyosmium/latest/reference/Handler-Processing/),
[Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/).
