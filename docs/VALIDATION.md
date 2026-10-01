# Local pilot validation — 2026-10-01

Environment: Windows laptop, Python 3.13.15, Node 24.19.0, installed Microsoft
Edge driven by Playwright 1.58.2. MapLibre GL JS 5.20.0. All figures below are
measured locally; none establish performance on a physical phone.

## Correctness and review

- 16 deterministic unit tests passed (`python -m unittest discover -s tests -v`).
- Python compilation and JavaScript syntax checks passed; `git diff --check` passed.
- Independent read-only review ran the original 14 tests and reviewed the metric,
  halo, source and viewer code. Its acquisition-category consistency finding was
  fixed with provenance validation and two regression tests. It found no blocking
  scoring/halo defect. Its source-completeness qualification is documented in
  METRIC-V2.md; its performance-test gap was fixed with explicit desktop gates.
- Synthetic lattice: 1,825 graph nodes, 150 POIs, 2,500 queries; global 0.0343 s,
  nine chunks 0.2244 s, maximum score difference 0.0. Overlapping halos cost more
  than a global solve on this deliberately small graph.
- Final real-data validation sampled 359 grid cells: 133 near chunk seams and 122
  at region edges (categories overlap). Unchunked and chunked float64 scores were
  identical; maximum float32 storage difference was 0.00000128033. The comparison
  took 25.37 s. This checks the acquired source, not global OSM completeness.

## Boston build

Coverage is central Boston plus nearby Cambridge:
`[-71.085, 42.345, -71.045, 42.375]` (west, south, east, north).
It is not all Greater Boston. Two broader requests exceeded the 50 MiB response
cap and stopped; the bounded smaller source succeeded at 23,230,696 bytes.

- Source timestamp: 2026-10-01T02:02:04Z.
- Source SHA-256: `11fc815bc57c4189ee0c98b545df413eff826dc2101305d4090fd7ceffc4e6a0`.
- Dataset: `9045a07db0150bab`; local output: `build/boston-final`.
- Graph: 116,080 nodes / 133,003 edges; 3,398 POIs across source including halo.
- Grid: 18,632 cells, of which 16,190 have a reachable snap.
- Four chunks; largest chunk 66,134 nodes; 5,948 reverse searches.
- Extraction/indexing: 1.682 s; scoring: 8.956 s; total build: 11.157 s.
- Analytic float32 scores: 74,528 bytes. Raster pyramid: 18 PNGs, 221,289 bytes.
- Raw maximum score: 56.0327; values above 30 saturate the fixed display scale.

## Final browser checks

`npm run test:browser -- build/boston-final` passed functional checks and all
explicit desktop simulation gates. Each viewport ran 100 scripted pan/zoom
operations, outside-coverage and return-home checks, and an overlay toggle.
The missing-manifest error message was separately verified. External requests
were disabled; no automated traffic went to public OSM basemap servers.

| Measurement | Desktop 1440×900 | Phone-sized 390×844 |
|---|---:|---:|
| Fresh-page overlay load on loopback | 1,734 ms | 238 ms |
| p95 animation frame interval | 16.9 ms | 16.9 ms |
| Pan-phase long tasks | 0 | 0 |
| Final post-GC JS heap | 6,696,876 B | 6,067,204 B |
| Heap growth after warmup sample | 296,984 B | 494,664 B |
| PNG requests | 13 | 15 |
| JS errors / failed HTTP responses | 0 / 0 | 0 / 0 |

Both layouts were screenshot-reviewed: controls and attribution remain visible,
the layout does not overflow horizontally, and the tile overlay renders. One
63 ms desktop startup task occurred before panning; none occurred in the mobile
viewport run. The same browser process was reused, so the second viewport benefits
from a warmed browser/GPU environment. These are not mobile-network cold-start
comparisons. JS heap is not GPU or total browser memory.

Gates: <=3 s fresh-page load on loopback, <=33 ms p95 frame interval, <=2 MiB
post-warmup JS heap growth, and at most two pan-phase long tasks. The measured
short run suggests bounded cache behavior; a ten-minute physical-phone memory
test remains outstanding. Raw local evidence is in `qa-artifacts/` (ignored).

## Not run / release limits

Physical iPhone Safari and Android Chrome, throttled cellular networks, production
CDN/object-store cache behavior, basemap-provider load tests, Windows process/GPU
peak-memory profiling, and Python 3.12 execution were not tested. Installed package
metadata allows Python 3.12 for the pinned dependencies, but that is not a tested
cloud environment. No cloud resources, public site, PR or push were created.

Known metric approximations: straight snap connectors are not barrier-aware;
relation POIs use bounds centers; conditional access and building levels are not
fully modeled; distinct OSM objects may describe the same business. These are
documented limitations rather than claims of exact entrance routing or safety.
