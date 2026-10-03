# Local Massachusetts raster archive

This opt-in prototype packages the existing dataset `5124e42eb1483a75`. It does
not alter scores, recolor or re-encode PNGs, modify the export, or change production
delivery. The healthy production viewer remains at
https://friendliness-index.pages.dev, deployment
https://3c407db9.friendliness-index.pages.dev (UI commit `82952d6`).

## Packaging and correctness

| Measure | Loose PNGs | PMTiles v3 |
|---|---:|---:|
| Raster objects to host | 9,478 | 1 |
| Internal raster tiles | 9,478 | 9,478 |
| Bytes | 147,227,322 | 147,249,624 |

The archive adds 22,302 bytes (0.0151%): a 127-byte header, a 42-byte root directory,
1,482 bytes of compressed metadata, and 20,651 bytes of leaf directories. All
9,478 PNG payloads are unique. This is a packaging/object-count improvement,
not image compression or a reduction in geographic detail.

Local artifact: `build/archives/massachusetts-5124e42eb1483a75.pmtiles`
(140.428 MiB). SHA-256:
`876b2af034895c8abd6fbf9a957beca5e3e47b9954f316dd1f5407fd5409b2e7`.

The Python 3.8.1 PMTiles writer stores original PNG bytes in Hilbert order, with
PNG payload compression set to `NONE`. Its reader enumerated the complete tile
index, verified no missing or extra entries, and compared every extracted tile
directly against the source file. The independent JavaScript 4.5.0 reader then
read all 9,478 addresses and verified their size and SHA-256 against the source
inventory. Both readers verified metadata and four absent tiles (Hartford,
Providence, Nashua, and Atlantic ocean). Absent tiles return no payload.

Header checks cover PNG type, zooms 7–14, clustering, counts, and exact bounding
coordinates `[-73.5082102, 41.1888589, -69.8601042, 42.8867783]`. Metadata retains
256-pixel tile size, metric version, parameters, source extracts/timestamp
(`2026-10-01T20:22:06Z`), attribution/license, and scoring/provenance hashes.
The original analytical float32 grid and its 426 raw parts remain separate and
unchanged; a PNG archive does not replace numerical score data.

Byte equality preserves every alpha and color value. Explicit examples in tile
`14/4863/6079` retain transparent `[34,62,92,0]` at `(0,0)` and the zero-score
palette color `[34,62,92,210]` at `(47,0)`. The latter checks color/alpha preservation;
a quantized PNG color alone cannot prove the underlying score was exactly zero.

Packaging plus complete Python verification took 23.044 seconds, with a sampled
peak working set of 45,699,072 bytes. The monitor's memory/wall-clock budgets were
not exceeded. Reports are in `qa-artifacts/pmtiles/package.json`,
`tile-inventory.json`, `independent-reader.json`, and
`qa-artifacts/pmtiles-package.resources.json`.

## Local browser validation

`scripts/pmtiles-preview.cjs` serves the existing export twice on loopback:
`/loose/` uses original PNG URLs, while `/archive/` injects the pinned official
PMTiles protocol and replaces only the score source in memory. Its manifest omits
the 9,478-entry availability list. Production `web/` and `build/massachusetts/`
files are never rewritten by this server.

This MapLibre 5.20.0 integration needed a small missing-raster adapter: the stock
protocol returns `data: null` for an absent raster, which left the map's tiles
pending in the initial test. The adapter lazily loads the existing transparent
PNG once and returns its bytes for absent raster results. It does not fabricate
score data or store extra archive tiles. The SDK still handles archive indexing,
range retrieval, decompression, and cancellation.

The HTTP server streams byte ranges instead of loading the archive into RAM.
Checks passed for a header range, suffix range, open-ended range, HEAD, invalid
and unsatisfiable ranges (416), and rejecting an un-ranged archive GET in this
prototype. All browser archive requests returned 206 with byte ranges; the
largest completed range was 191,773 bytes. No browser downloaded the full archive.

Browser QA passed at 1440×900, 390×844, and 320×568. Each mode visited the statewide
overview, Boston, Pittsfield, Nantucket, Vineyard Haven, Cuttyhunk, Hartford,
Providence, Nashua, and North Adams, then checked overlay toggling and Home.
Coverage labels, compact controls, attribution, and no horizontal overflow passed.
There were no page/console errors, failed HTTP responses, or external requests.
All 30 pairs of final viewport screenshots were pixel-identical (zero differing
pixels). The `?offline=1` QA path suppresses the OSM basemap so both delivery modes
can be compared deterministically. These are desktop-browser phone-sized views,
not physical-phone or cellular-network tests.

### Measured cold overview traffic

| Viewport | Delivery | HTTP requests | Response body bytes | CDP encoded bytes |
|---|---|---:|---:|---:|
| 1440×900 | PNG | 27 | 2,619,612 | 2,626,484 |
| 1440×900 | PMTiles | 30 | 2,515,583 | 2,524,850 |
| 390×844 | PNG | 10 | 1,444,861 | 1,447,517 |
| 390×844 | PMTiles | 13 | 1,340,832 | 1,344,623 |
| 320×568 | PNG | 10 | 1,444,861 | 1,447,517 |
| 320×568 | PMTiles | 13 | 1,340,832 | 1,344,623 |

Each run used a fresh browser context with normal caching and no request routing.
The local server does not gzip/Brotli assets. Counts cover the viewer, scripts,
styles, manifest, boundary, and score requests; the empty favicon response is
excluded from server request counts. CDP reports completed encoded transfers,
including response headers. These measurements do not predict production CDN
compression, latency, or billing.

PMTiles removes 151,317 manifest bytes but adds the SDK, adapter, and archive index
reads. Net response body savings on each cold overview were 104,029 bytes, with
three extra HTTP requests. At 390 px, raster/index requests changed from 3 requests
and 86,315 bytes to 5 requests and 112,582 bytes. Packaging does **not** mean the
browser downloads one object in one request. Cold local loads were not faster:
desktop PNG/PMTiles was 941/1,768 ms, and 390 px was 958/1,487 ms, including the
same 350 ms settling delay. These are single local runs, not latency benchmarks.

Per-location and return-home records remain in
`qa-artifacts/pmtiles/browser/results.json`. Animated Home can request and cancel
intermediate zoom tiles; server-completed body counts and CDP completed-transfer
bytes therefore need not agree for that portion of the journey. Use the stable
cold-overview rows above for the direct comparison. Screenshot evidence and
`pixel-comparison.json` are in the same directory.

## Reproduce locally

Use the project's Python environment (including Pillow), Node, Playwright, and
installed Edge. `requirements-archive.txt` pins and hashes the Python wheel.
The validation run imported the verified wheel directly through `PYTHONPATH`:

```powershell
$env:PYTHONPATH=(Resolve-Path '.tools/pmtiles/pmtiles-3.8.1-py3-none-any.whl').Path
.\.venv\Scripts\python.exe scripts/package-raster.py build/massachusetts build/archives/new-check.pmtiles --report qa-artifacts/pmtiles/new-check.json
```

The packager refuses to overwrite an archive and verifies a temporary file before
renaming it. The example uses a new output name. Alternatively install the pinned
wheel into the project environment using `pip install --require-hashes -r
requirements-archive.txt`. The SDK's locked manifests are checked in under
`scripts/archive-deps/`; copy them to `.tools/pmtiles/js/` and run `npm ci --prefix
.tools/pmtiles/js --ignore-scripts --no-audit --no-fund` when preparing a new machine.

From the repository root, with project dependencies available:

```powershell
node scripts/verify-raster-archive.cjs
node scripts/pmtiles-browser-qa.cjs
.\.venv\Scripts\python.exe scripts/compare-pmtiles-screenshots.py
node scripts/pmtiles-preview.cjs 8787
```

Open http://127.0.0.1:8787/archive/?offline=1 or
http://127.0.0.1:8787/loose/?offline=1. Omit `offline=1` for the normal OSM basemap;
the recorded comparison uses offline mode. No remote service is created.

## Hosting proposal requiring approval

Keep the frontend on existing Pages. Place this one immutable MA archive on a
host that supports browser GET byte ranges, 206/Content-Range, stable ETags, and
CORS. Pages itself cannot hold this artifact: its per-asset limit is 25 MiB, and
its documented range behavior currently returns 200 rather than 206.
Sources: [Pages limits](https://developers.cloudflare.com/pages/platform/limits/)
and [Serving Pages](https://developers.cloudflare.com/pages/configuration/serving-pages/).

A concrete next scope is **one R2 Standard bucket containing only the public MA
raster archive**, with one user-approved dedicated hostname on an existing
Cloudflare-managed domain, and GET/HEAD CORS for
`https://friendliness-index.pages.dev`. Permit the Range request header and expose
ETag, Content-Range, Accept-Ranges, and Content-Length. Use an immutable object key
including the dataset and archive content hash, and a long immutable cache policy.
No Worker or dynamic tile service is required for direct PMTiles reads. Keep raw
float32 parts on Pages in this first step. Following migration, the current export
would have about 439 served objects (438 Pages assets including the SDK, plus one
archive), versus 9,915 today. Upload-input counts are one larger because `_headers`
is processed rather than served. The 426 analytical parts are still objects.

The chosen hostname/domain, public-read bucket scope, billing allowance, and
permission to switch the live viewer must be explicit before provisioning or
deployment. R2's `r2.dev` endpoint is intended for development and rate-limited;
it is not the proposed production URL. Cross-origin behavior must be tested on
the approved endpoint before any live switch. Sources:
[R2 public buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/)
and [CORS](https://developers.cloudflare.com/r2/buckets/cors/).

R2 Standard currently includes 10 GB-month storage, 1 million Class A and
10 million Class B operations monthly; Internet egress is free. This MA archive
alone fits well within the storage allowance, but traffic and other account use
can exceed free allowances. No zero-cost guarantee or hard spending cap is
implied. Confirm account-level usage and an approved spending limit before enabling
the service. [R2 pricing](https://developers.cloudflare.com/r2/pricing/).

For broader coverage, use immutable regional archives plus a small versioned
catalog and fetch only intersecting regions. Do not put the whole country into
one unbounded artifact or infer national costs from this one-state test. Validate
cross-region boundaries and preserve the existing source halo/scoring method.

Before a future switch: validate range/CORS/ETag/cache behavior on the actual host,
repeat desktop/mobile rendering checks from a Pages preview, and compare actual
network latency. Retain the current PNG deployment as rollback. No bucket,
credential, domain, security setting, paid resource, or production archive route
was created or changed during this local prototype.
