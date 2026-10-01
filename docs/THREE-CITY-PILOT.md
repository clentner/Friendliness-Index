# Continuous Boston, Cambridge and Somerville pilot

This expansion reuses the fixed v2 metric, 975 m halo and raster renderer. It
increases only the authorized source/graph safeguards, updates the generic area
label, and makes the seam test efficient for sparse samples on a larger graph.
No city boundary is used to partition, normalize, download or render the scores.

## Coverage and source

Requested bounds (west,south,east,north):
`[-71.16, 42.33, -71.025, 42.42]`.
The projected grid rectangle is about 116.65 km². It includes central Boston,
Back Bay/Fenway/Allston, Cambridge and Somerville's urban area. It does not claim
every administrative corner of Boston, southern Dorchester, Hyde Park, or the
entire eastern harbor/airport area.

Acquisition bounds, including the conservative halo:
`[-71.17554328118166,42.31830810531153,-71.00969438831704,42.43167837458685]`.

One bounded request to the public Overpass API succeeded in 16.02 seconds:
81,821,546 bytes (about 78.03 MiB). No automatic retry loop or tile-server scraping
was used. Source timestamp: 2026-10-01T02:20:19Z. Source SHA-256:
`63ddccfe20378732304a5213600421012cd87ef450b02358450a99cc33122e9f`.
This is well below the explicitly authorized 250 MiB acquisition limit.

## Measured build

- Local output: `build/three-cities`; dataset: `43618671d5d41436`.
- 502,138 graph nodes, 561,407 edges and 8,498 source POIs including the halo.
- 187,005 cells (411×455); 172,721 have a reachable graph snap.
- 36 chunks; largest chunk 67,898 nodes; 25,189 reverse searches.
- Extraction/indexing 7.207 s; scoring 34.958 s; total build 44.627 s.
- External wall-clock monitor: 46.036 s; measured peak process working set
  866,349,056 bytes (826.21 MiB). Minimum available system RAM during the build:
  1,325,334,528 bytes (1.23 GiB). This passed the 15-minute / 1.5-GiB safeguards.
- 61 PNG tiles, 1,897,389 bytes; raw float32 scores 748,020 bytes.

Initial system check found 354.6 GB free disk and 2.47 GiB available RAM. The
download's process-RAM reading tracked the Windows venv launcher, not the actual
interpreter, so it is not reported as a download peak-memory measurement. The
build monitor used the actual interpreter process and its measurement is valid.

## Browser checks

Real-data seam validation passed on 358 samples, including 167 near chunk seams
and 123 on the outer grid boundary (categories overlap). Maximum chunk versus
independent forward-reference difference was 1.07e-14; maximum float32 storage
difference was 8.39e-7. The comparison took 35.27 seconds. The original test's
global reverse-source reference hit its 120-second safeguard on this larger
graph; the corrected test uses one forward query per sample instead. It checks
the same mathematical metric without changing production scoring.

Both desktop and phone-sized Windows Edge viewports passed 100 pan/zoom
operations, all functional checks, and all desktop performance gates. The script
blocks external requests, so automated QA does not hit OSM basemap servers.

| Measurement | 1440×900 | 390×844 |
|---|---:|---:|
| Fresh-page overlay load, loopback | 1,912 ms | 321 ms |
| p95 frame interval | 16.8 ms | 16.8 ms |
| Pan-phase long tasks | 0 | 0 |
| Final post-GC JS heap | 8,116,056 B | 7,293,592 B |
| Post-warmup heap growth | 383,552 B | 552,080 B |
| PNG requests | 54 | 56 |
| JS errors / failed requests | 0 / 0 | 0 / 0 |

The desktop startup had 50 ms and 110 ms tasks; neither occurred during panning.
These are desktop/loopback observations with a warmed browser for the second
viewport, not real-phone, cellular, or total GPU-memory results. Screenshots of
both layouts were reviewed. A seam-reference process also ran during this QA.

## Reproduce

```powershell
.venv\Scripts\python -m pilot.build download --bbox=-71.16,42.33,-71.025,42.42 --source data/boston-cambridge-somerville.json
.venv\Scripts\python -m pilot.build build --bbox=-71.16,42.33,-71.025,42.42 --source data/boston-cambridge-somerville.json --out build/three-cities --seconds 900
.venv\Scripts\python scripts/real-seams.py data/boston-cambridge-somerville.json build/three-cities/manifest.json
npm run test:browser -- build/three-cities
```

Reuse existing source files; the downloader refuses to overwrite them. Generate
into a new output path if rebuilding. The `--seconds` search deadline is not a
whole-process memory or wall-clock limiter; the reported expanded build used a
separate local process monitor for those safeguards.

All earlier data limitations remain: straight connectors are not barrier-aware,
relation centers stand in for entrances, conditional access/levels are incomplete,
OSM object duplicates can represent the same business, and bbox source selection
does not prove completeness for unusually long crossing ways. Physical phones,
cellular loading and production hosting are still unvalidated. Source/generated
data remain local and ignored by Git.
