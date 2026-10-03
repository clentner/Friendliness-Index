# Massachusetts archive cutover preparation

The user approved R2 activation, one public Massachusetts archive at
`tiles.chrislentner.com`, attaching Pages at `maps.chrislentner.com`, and the
verified archive cutover. They accepted $5/$10 billing alerts with possible
overages, rather than a hard spending cap. A separate browser operator owns
Cloudflare settings. This checkout prepares the viewer and performs local QA;
it must not race that operator or start a new OAuth/credential flow.

## Browser upload handoff

Original verified artifact:
`build/archives/massachusetts-5124e42eb1483a75.pmtiles`.

A byte-identical copy with the correct object filename is staged at:
`build/r2-upload/ma/5124e42eb1483a75/876b2af034895c8a.pmtiles`.

- Bucket: `friendliness-index-rasters` (browser operator confirms availability).
- Navigate/create prefix `ma/5124e42eb1483a75/`, then upload the staged file.
- Exact object key: `ma/5124e42eb1483a75/876b2af034895c8a.pmtiles`.
- Exact size: **147,249,624 bytes**.
- SHA-256: `876b2af034895c8abd6fbf9a957beca5e3e47b9954f316dd1f5407fd5409b2e7`.
- Content-Type: `application/vnd.pmtiles`.
- Cache-Control: `public, max-age=31536000, immutable`.
- Content-Encoding: unset; upload the original archive without external gzip.
- Optional custom object metadata `sha256`: the full hash above. Do not set ETag
  manually; Cloudflare supplies it and it is not necessarily a SHA-256.

Intended URL:
`https://tiles.chrislentner.com/ma/5124e42eb1483a75/876b2af034895c8a.pmtiles`.
Creating folders or selecting a upload prefix must not duplicate `ma/` in the key.
Record the actual URL and metadata after upload. Report any UI metadata control
that is unavailable instead of claiming it was set.

The browser operator's CORS configuration should permit GET/HEAD from
`https://maps.chrislentner.com` and `https://friendliness-index.pages.dev`, allow
Range, and expose ETag, Content-Range, Accept-Ranges, and Content-Length. Permit
only an explicitly chosen preview origin if live preview QA needs one. The
archive is public; CORS is not authentication. Keep original account-wide
security settings and scope cache eligibility to the approved archive hostname.

## Local production bundle

`deploy/ma-archive.json` is the reviewed configuration. The browser client uses
`manifest.archive_url` when present and retains PNG delivery for older manifests.
The official PMTiles 4.5.0 SDK is version-locked and vendored with its BSD license
and the bundled fflate license. Absent raster addresses use the original
transparent image, preserving no-data semantics and allowing MapLibre to settle.

Run `python scripts/prepare-archive-site.py` from the repo root to stage
`build/massachusetts-pmtiles`. It refuses to overwrite a staged site, verifies the
archive size/hash, omits the 9,478 PNG raster objects, and preserves the original
`build/massachusetts` export. No scoring code or data is rebuilt.

The prepared Pages directory contains **441 upload inputs, 175,551,041 bytes**.
The `_headers` input is processed rather than served, leaving 440 served Pages
assets plus one R2 object. All **426 raw float32 parts (174,044,160 bytes)**, raw
index, coverage, and dataset provenance are retained byte-for-byte. The immutable
dataset metadata records the original PNG export; the top-level manifest selects
the current delivery method. The rollback source's 9,916 files are hash-unchanged.

Local QA commands (with Playwright and Edge available):

```powershell
$env:PMTILES_PRODUCTION_ROOT='build/massachusetts-pmtiles'
$env:PMTILES_QA_OUTPUT='qa-artifacts/pmtiles-production/browser'
node scripts/pmtiles-browser-qa.cjs
python scripts/compare-pmtiles-screenshots.py qa-artifacts/pmtiles-production/browser
```

The local production test serves the staged files as-is and intercepts only the
exact configured HTTPS archive URL, forwarding its ranges to the local verified
file. It compares 30 views against PNG delivery at desktop and two phone widths.
This verifies client/configuration compatibility; it is **not** live TLS, DNS,
CORS, cache, or cellular-network verification. Per-request/viewport results live
under `qa-artifacts/pmtiles-production`. The original prototype measurements in
`docs/PMTILES-PROTOTYPE.md` are a separate run and must not be relabeled production
measurements.

The prepared production configuration passed this local test: all six runs
(PNG/archive at 1440×900, 390×844, and 320×568), all 30 screenshot pairs with zero
differing pixels, sparse missing-tile handling, coverage labels, Home/overlay
controls, attribution, and overflow checks. No page/console errors or failed HTTP
responses were recorded. The range server checks also passed. This result leaves
live endpoint verification pending and does not authorize deployment before the
browser operator confirms readiness.

## Before publishing

Wait for the browser operator to confirm endpoint readiness. Then use read-only
requests to verify actual object size, PMTiles header/metadata, several original
tile hashes, missing tiles, HTTPS, 206/Content-Range/ETag, CORS from both approved
frontend origins, and cache behavior. Exercise the real archive endpoint from
desktop and phone-sized browser contexts. Report physical-device testing limits;
physical-device testing is not represented by phone-sized desktop viewports. The
user subsequently authorized this cutover after real-endpoint browser QA; the
older physical-phone gate in `deploy/README.md` is superseded for this cutover.

Only after those checks, deploy `build/massachusetts-pmtiles` to the existing
`friendliness-index` Pages project, using its existing direct-upload production
branch `main`. Do not create a new Pages project or alter the Git repository's
`master` branch name to match Pages. Verify both approved website origins after
deployment, including that the mobile blurb stays absent and attribution remains.
Record the immutable deployment URL and commit in the deployment receipt.

## Rollback

Preserve https://3c407db9.friendliness-index.pages.dev and the unchanged
`build/massachusetts` PNG export. Restore that Pages deployment, or redeploy the
preserved export, if archive delivery fails. Keep the immutable R2 object available
while cached archive clients may still reference it. Restoring the frontend does
not require changing DNS, deleting the bucket, removing billing alerts, or
discarding analytical data.
