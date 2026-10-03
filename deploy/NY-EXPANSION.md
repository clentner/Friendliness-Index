# New York expansion: local preparation, publication not authorized

The full NY scoring pass, export, archive packaging and local browser QA are
complete. This document records the exact reviewed artifacts and incremental
hosting footprint. Publication still requires approval; no NY asset has been
uploaded and Massachusetts production and rollback data remain intact.

## Additive site layout

- Preserve Massachusetts at `https://maps.chrislentner.com/` and
  `https://friendliness-index.pages.dev/`.
- Add New York at `/ny/` on those same origins. Its viewer, provenance and raw
  float32 files are self-contained under that prefix.
- Put a persistent, accessible region switch on both maps, visibly labelled
  "Massachusetts" and "New York State", with the current region highlighted.
  New York is discoverable from the existing MA landing page. The compact
  control sits above the bottom attribution, separate from the existing Home,
  score toggle and zoom controls; verify it at 320 px and 390 px phone widths.
- Store immutable NY PMTiles objects under a new `ny/<dataset>/` prefix in the
  existing `friendliness-index-rasters` bucket, served by
  `https://tiles.chrislentner.com`. Do not replace the existing MA object.
- Use the measured archive size to decide the object count. Each object must
  remain below the conservative 512,000,000-byte cache ceiling. Browser QA must
  prove range-only delivery and visual equality with the loose PNG export.
- No new service, domain, account plan, credentials, CORS or security setting is
  required by this proposed layout. Existing allowed website origins are reused.

`scripts/prepare-multi-region-site.py` creates a new local combined directory.
It requires the preserved 441-input / 175,551,041-byte MA staging baseline,
verifies 439 MA served assets byte-for-byte, retains its root manifest, app
logic, data and archive URL, and copies the NY staging under `/ny/`. MA's
`index.html` gains only the region switch and a shared navigation stylesheet;
NY receives the same control. `_headers` retains its existing bytes as a prefix,
followed by cache rules specific to `/ny/datasets/*` and `/ny/manifest.json`.
Existing security rules do not change.
The script counts the combined inputs, added served assets and exact added bytes,
checks Pages limits, and verifies both source staging directories are unchanged.
It contains no publication command.

## Evidence required for review

Local verification is complete. NY is **ready for publication approval**, with
live endpoint verification still required after an approved archive upload.

| Hosting item | Existing MA | Proposed MA + NY | Exact increment |
| --- | ---: | ---: | ---: |
| Pages upload inputs (including `_headers`) | 441 | 2,637 | 2,196 |
| Served static assets | 440 | 2,636 | 2,196 |
| Uncompressed staging bytes | 175,551,041 | 1,070,734,523 | 895,183,482 |
| R2 archive objects | 1 | 3 | 2 |
| R2 archive bytes | 147,249,624 | 708,392,102 | 561,142,478 |

The largest static asset is **1,106,773 bytes**. The Pages bundle is
`build/ma-ny-pmtiles`; 439 original MA served assets are byte-identical, including
the MA map logic, manifest, data and archive URL. The only changed existing
served asset is root `index.html`, which adds the region switch and stylesheet.
Existing `_headers` bytes remain an exact prefix, with 113 additional bytes for
NY caching. The original MA and NY staging directories were verified unchanged.
No archive is included in Pages and no analytical raw data is added to R2.

All 39 regression tests pass. All 52,433 PNG payloads pass two independent
archive readers. All 63 loose-PNG/archive screenshot pairs are pixel-identical.
The combined bundle passes 12 MA → NY → MA navigation views across 1440, 390 and
320 px widths, with all three archives exercised by Range-only requests, no
page errors, no failed requests and no layout overflow. The 320 px NY overview
and 390 px NY detail captures were also visually inspected, including navigation
and attribution placement.

Cold NY archive bodies are **493,308 / 133,879 / 48,191 bytes** at those widths,
from 11 / 7 / 5 Range requests. The largest individual Range in the full raster
tour is 209,911 bytes. None of the browser runs downloads an archive whole.
The existing animated Home transition adds intermediate tile requests; see
`docs/NEW-YORK.md` and `qa-artifacts/ny/browser/results.json` for separate cold,
tour and warm-return measurements. Requests may reach R2 or be served by edge
cache; local test counts do not determine monthly billed Class B operations.

Exact production archive URLs were tested through a loopback interceptor with
local CORS response headers. This validates client routing and partial reads,
not live Cloudflare behavior or physical-phone/cellular performance. The existing
bucket policy must still admit GET/HEAD and Range from both approved frontend
origins and expose ETag, Content-Range, Accept-Ranges and Content-Length. No
policy change is proposed. Verify the existing policy and edge cache against
the two actual uploaded objects before frontend cutover.

- `qa-artifacts/ny/verification.json`: analytical cells, hashes, no-data, PNG
  inventory and source-access verification.
- Archive packaging and independent JavaScript reader reports: exact archive
  bytes/hash, complete byte-for-byte PNG verification, missing-tile behavior.
- Browser results and pixel comparisons at desktop and two phone widths:
  configured URLs, cold/warm range request counts and bytes, zero full-archive
  GETs, no page errors and exact raster rendering agreement.
- `scripts/combined-region-browser-qa.cjs` verifies actual MA -> NY -> MA link
  navigation in the staged combined bundle at all three widths, current-region
  labels, no overflow, correct dataset/archive selection and range-only reads.
  It intercepts archive and basemap requests locally; it does not claim live
  endpoint or cellular-network verification.
- NY staging and combined-site inventories: exact incremental R2 objects/bytes,
  Pages inputs/bytes, largest asset, and preserved MA assets.
- Conditional billing estimate using the actual bytes and measured requests.
  Account-wide free-tier usage and future traffic are unknown, so artifact size
  must not be presented as a guaranteed dollar bill.

The existing static architecture uses no Pages Functions. Static asset requests
are [free and unlimited](https://developers.cloudflare.com/pages/functions/pricing/#static-asset-requests).
The current [Pages limits](https://developers.cloudflare.com/pages/platform/limits/)
are 20,000 files on Free and 25 MiB per asset. The browser drag-and-drop uploader
has a separate [1,000-file limit](https://developers.cloudflare.com/pages/get-started/direct-upload/#limits);
the existing Wrangler workflow supports 20,000. Do not introduce an OAuth flow
if existing authorized deployment access is unavailable.

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

These bytes are 0.561142478 decimal GB. At the current R2 Standard storage rate,
the unrounded marginal calculation is $0.00841713717/month before free allowances
and billing-unit rounding; it is **not a promised bill**. The known project
archives fit within the account-wide 10 GB-month allowance, but other usage is
unknown. Upload and Range-read charges likewise depend on available Class A/B
allowances, rounding, requests and edge cache hits. R2 egress has no charge.
See [R2 pricing](https://developers.cloudflare.com/r2/pricing/).

### Reviewed execution sequence

1. Upload only the reviewed immutable NY archive object(s), with PMTiles content
   type, `public, max-age=31536000, immutable`, and no external content encoding.
2. Verify each exact public URL with Range/HEAD, content length, bytes, CORS and
   cache behavior before deploying a frontend that references it. If any check
   fails, keep MA production unchanged and report the failure.
3. Deploy `build/ma-ny-pmtiles` to the existing `friendliness-index` Pages project
   using its existing direct-upload production branch `main`. Repository code
   remains on `master`; pushing code does not perform this manual deployment.
   Preserve the current MA deployment and its original loose-PNG rollback.
4. Verify both `/` and `/ny/` on both established origins, including range-only
   archive requests and absence of MA asset/configuration regressions.

Preserved rollback references: MA commit
`0a3d795e6d4bb37f2b573dbdfc4947fc01e53e46`, archive deployment `36133e09`, and
loose-PNG deployment `3c407db9`. The MA PMTiles file remains
`build/archives/massachusetts-5124e42eb1483a75.pmtiles`, SHA-256
`876b2af034895c8abd6fbf9a957beca5e3e47b9954f316dd1f5407fd5409b2e7`.
No rollback data is deleted or replaced by local NY preparation.
