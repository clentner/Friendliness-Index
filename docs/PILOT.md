# Run the unpublished Boston pilot

The new pilot is opt-in; `generate.py`, its PBF workflow and legacy outputs remain
unchanged. Use Python 3.13 and Node 24 (other versions have not been validated).

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-pilot.txt
npm ci --ignore-scripts
npm run vendor
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m scripts.benchmark
```

The current machine has isolated Python in `.tools/python`, uv in `.tools/uv`,
and the ready environment in `.venv`. No PATH changes or cloud credentials are
required. The lockfiles pin the tested dependency set.

## Source and build

The first supported area is central Boston and part of Cambridge, not all of
Greater Boston. A larger initial bounding box exceeded the 50 MiB source cap;
the bounded pilot successfully uses this smaller extent:

```powershell
.venv\Scripts\python -m pilot.build download --bbox=-71.085,42.345,-71.045,42.375 --source data/boston-central.json
.venv\Scripts\python -m pilot.build build --bbox=-71.085,42.345,-71.045,42.375 --source data/boston-central.json --out build/boston-v2 --seconds 180
.venv\Scripts\python -m http.server 8000 --bind 127.0.0.1 --directory build/boston-v2
```

Open http://127.0.0.1:8000. Existing source/build paths are refused rather than
overwritten. Reuse the acquired source; use a fresh output directory after code
changes. Public Overpass is used only for explicit bounded acquisition, never
for panning. Requests have server time/space limits and a 50 MiB response cap;
there is no automatic retry loop. Data provenance accompanies each extract.

Ordinary viewer use requests OSM basemap tiles. Automated QA uses `?offline=1`,
which disables all external tiles and exposes a local inspection hook. This
keeps automated pan tests off the public OSM tile service. The overlay and bundled
MapLibre assets work entirely from the local static directory in this mode.

```powershell
npm run test:browser -- build/boston-v2
.venv\Scripts\python scripts/real-seams.py data/boston-central.json build/boston-v2/manifest.json
```

QA uses existing Microsoft Edge in headless mode, desktop and phone-sized
viewports, repeated pan/zoom, screenshots, errors, tile responses, overlay toggle
and post-GC JS heap samples. It is not a physical phone, GPU-memory measurement,
or a mobile-network benchmark. See `qa-artifacts/browser-results.json` locally.
The final check performs 100 pan/zoom operations per viewport. Its desktop-only
gates are cold load <=3 seconds, p95 frame interval <=33 ms, post-warmup heap
growth <=2 MiB and at most two pan-phase long tasks. Startup long tasks are
reported separately. These short-run gates do not establish a ten-minute phone
memory plateau or mobile-network readiness.

## Output

- `index.html`, `app.js`, `style.css`, `vendor/`: static frontend.
- `manifest.json`: current immutable dataset reference and provenance.
- `datasets/<content-id>/tiles/{z}/{x}/{y}.png`: raster levels 9–14.
- `datasets/<content-id>/scores.f32`: row-major little-endian analytic values.
- `datasets/<content-id>/metadata.json`: grid affine transform and full provenance.

There is no browser graph, per-cell GeoJSON, browser scoring, user telemetry,
account, backend scoring service or runtime database. Browser cache size is
explicitly bounded; only visible/nearby MapLibre tiles are requested.

Fixed metric meaning and known spatial approximations are in [METRIC-V2.md](METRIC-V2.md).
Source data, generated builds, runtimes and screenshots stay ignored by Git.
The OSM extract and derived dataset need ODbL attribution/compliance when released;
the repository's code-license decision remains with its owner.

## Current scope limits

The pipeline retains the small source graph and grid in RAM, then scores bounded
chunks. It is a metro pilot, not a national preprocessing system. There is no
PBF importer in the new path yet; legacy PBF tooling remains available separately.
Raster delivery supports this fixed score/palette; exact value lookup and category
sliders would require a separately designed numeric-tile interaction layer.
