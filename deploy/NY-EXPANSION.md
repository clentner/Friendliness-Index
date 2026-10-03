# Continuous MA + NY publication plan — approval pending

The reviewed final local candidate is `build/ma-ny-continuous-final`, display
identity `159c1e74953cb90e`. The user requested one seamless map, replacing the
previous region-switch design. Repository merge/push is authorized; archive upload
and live frontend cutover still require explicit publication approval.
Production remains MA-only on the existing two origins. Nothing is uploaded.

## Final layout and hosting impact

Serve both states at `/` on `maps.chrislentner.com` and
`friendliness-index.pages.dev`. A single raster source routes tile addresses to
MA, NY overview, NY detail or an immutable locally composed shared tile. No
switcher or separate NY route is required. Raw-score clicks read the preserved
state blocks lazily using EPSG:32619. MA wins finite analytical overlap, and MA
nontransparent display pixels win composite overlap without accumulating opacity.

| Hosting item | Existing MA | Final MA + NY | Increment |
| --- | ---: | ---: | ---: |
| Pages inputs including `_headers` | 441 | 2,734 | 2,293 |
| Served static assets | 440 | 2,733 | 2,293 |
| Staging bytes | 175,551,041 | 1,074,012,573 | 898,461,532 |
| R2 objects | 1 | 3 | 2 |
| R2 archive bytes | 147,249,624 | 708,392,102 | 561,142,478 |

The final revision adds 97 inputs / 3,278,050 bytes versus the switcher candidate.
Largest static asset: 1,106,773 bytes. All 2,607 float32 parts are retained.
102 composite tiles occupy 4,044,676 bytes. The original MA archive and both NY
archives are unchanged. Root app, HTML and manifest change for continuous routing;
438 baseline inputs remain byte-identical, including existing `_headers` rules.
No archive is uploaded to Pages. Use the existing Wrangler direct-upload workflow;
no credentials, domains, paid services or network/security settings change.

## Verified evidence

All 2,734 staged assets match their saved hashes and current frontend source.
Both source staging dataset trees remain unchanged. Final staging took 11.03
monitored seconds at 61,304,832 bytes peak working set; final audit took 3.250 seconds.
41 Python tests and 8 JS checks pass. All 51 final screenshot pairs are pixel
identical across desktop and two phone widths. Each width checks 43 raw-score
fixtures against original data and pyproj. The 320 px Home overview fits both
states. Single-layer overlap, no switcher, Home, overlay, attribution, click
popup, no overflow/errors and overview/detail transitions are checked.

Cold overview archive bodies: 387,318 / 20,910 / 20,910 bytes from 11 / 3 / 3
Range responses at 1440 / 390 / 320 px. Cold encoded total browser transfers:
2,028,871 / 1,474,112 / 1,474,112 bytes. Cold views load neither raw blocks nor
NY detail. Boston and NYC detail avoid unrelated state archives. These local
intercepted tests do not establish real public Range/CORS/cache behavior.

Evidence is under `qa-artifacts/continuous/`: `preparation.json`,
`final-package-audit.json`, `staging-final.resources.json`, and
`browser-final/{results,pixel-comparison}.json`. Full transfer measurements and
historical data-build evidence are in [NEW-YORK.md](../docs/NEW-YORK.md).
The final bundle is local and unpublished. Refresh pricing/limits and verify
existing deployment access at publication time; no authentication or policy
changes are authorized by this preparation.

## After explicit publication approval

### Exact immutable R2 objects prepared locally

Bucket: `friendliness-index-rasters`. The object keys and hashes below are also
machine-readable in `deploy/ny-archives.json`. Neither object is published.
Verified hard links with exact object filenames are staged under
`build/r2-upload/ny/b42279c259905289/`; upload to that exact prefix once approved.

| Zooms | Object key | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| 5–12 | `ny/b42279c259905289/e25d3229b7a63897-overview.pmtiles` | 208,457,279 | `e25d3229b7a6389736b96990f92d6deaeb0f9e2c8a97e4880106d0c1d32ac30e` |
| 13–14 | `ny/b42279c259905289/0bd72787e5d19e51-detail.pmtiles` | 352,685,199 | `0bd72787e5d19e51520ea0f056a8d56131b8d5f521efe7c78058aa053e32c307` |

The exact added R2 storage is **two objects / 561,142,478 bytes**. Combined with
the preserved MA archive, these three known objects total **708,392,102 bytes**.
Each object stays below 512,000,000 bytes. Partitioning by zoom avoids introducing
a geographic split and keeps the frontend's single raster source/layer.
The 52,433 source PNG payloads all passed byte-for-byte verification by both
the Python packager and independent official JavaScript reader. Sparse missing
tiles return transparent display tiles. Native z14 samples retain the metric's
finite-zero blue; resampled overview tiles are not required to retain that exact
RGBA value after LANCZOS filtering.

These bytes are 0.561142478 decimal GB. The prior pricing comparison is
recorded in `docs/NEW-YORK.md`; refresh account-wide allowances and current
[R2 pricing](https://developers.cloudflare.com/r2/pricing/) before publication.
Local request counts do not determine billed origin operations or cache hits.
No new plan, service or account setting is proposed.

### Reviewed execution sequence

1. Upload only the reviewed immutable NY archive object(s), with PMTiles content
   type, `public, max-age=31536000, immutable`, and no external content encoding.
2. Verify each exact public URL with Range/HEAD, content length, bytes, CORS and
   cache behavior before deploying a frontend that references it. If any check
   fails, keep MA production unchanged and report the failure.
3. Deploy `build/ma-ny-continuous-final` to the existing `friendliness-index` Pages project
   using its existing direct-upload production branch `main`. Repository code
   remains on `master`; pushing code does not perform this manual deployment.
   Preserve the current MA deployment and its original loose-PNG rollback.
4. Verify `/` on both established origins, including continuous pan across both
   states, mobile Home framing, raw-score clicks, archive transitions and Range-only
   requests. No separate `/ny/` route is part of this candidate.

Preserved rollback references: MA commit
`0a3d795e6d4bb37f2b573dbdfc4947fc01e53e46`, archive deployment `36133e09`, and
loose-PNG deployment `3c407db9`. The MA PMTiles file remains
`build/archives/massachusetts-5124e42eb1483a75.pmtiles`, SHA-256
`876b2af034895c8abd6fbf9a957beca5e3e47b9954f316dd1f5407fd5409b2e7`.
No rollback data is deleted or replaced by local NY preparation.
