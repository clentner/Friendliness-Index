# Published continuous Massachusetts and New York map

Verified on 2026-10-03 at 23:53:13 UTC. The continuous map is live on both
[ maps.chrislentner.com ](https://maps.chrislentner.com) and
[ friendliness-index.pages.dev ](https://friendliness-index.pages.dev).

- Deployment source commit: `f869e788854a51d74645bb7b888a01b15ef9b650`.
- Pages deployment: `b60a08f4-c3b8-4b9c-9ee2-33e3ac87842b`, production branch `main`,
  immutable URL https://b60a08f4.friendliness-index.pages.dev.
- Candidate: `build/ma-ny-continuous-ui300`; display identity `ead61093d03122c6`.
- Pages: 2,734 inputs / 2,733 served assets / 1,074,013,041 uncompressed bytes.
  Wrangler uploaded 2,296 new files, reused 437, and reported 267.48 seconds
  for its upload phase. This is not a measured CLI network byte count.
- NY R2 increment: three immutable objects / 561,145,019 bytes. Both detail
  partitions are lossless, under the 300 MB browser cap. Original archives,
  datasets, scores and rollback artifacts are preserved.

## Public and live verification

Full public sizes and SHA-256 hashes match all three prepared NY archives.
Sampled range bytes match local files, with 206/Content-Range, stable ETag,
CORS from both production origins and cache HIT. All six real browser runs
(1440x900, 390x844, 320x568 on each origin) pass: 258 original float32/pyproj
fixtures, 34 critical served-asset hash checks, Home framing, MA/NY seam pans,
overview/z13/z14 transitions, one raster layer, lazy state routing, overlay,
click popup, attribution and no errors/overflow. All 114 live/reference screen
comparisons are pixel-identical. Two additional normal-basemap phone-sized views
pass and the live phone framing/basemap screenshots were visually inspected.
All 915 observed archive GETs use byte Range and return 206; map loading never
fetches a whole archive. The separate full-object verification downloads are
intentional QA and are not included in the range-only map claim.

| Origin | Width | Cold ranges | Cold archive body bytes | Cold total CDP encoded bytes |
| --- | ---: | ---: | ---: | ---: |
| maps.chrislentner.com | 1440 | 11 | 387,318 | 1,000,377 |
| maps.chrislentner.com | 390 | 3 | 20,910 | 447,766 |
| maps.chrislentner.com | 320 | 3 | 20,910 | 447,747 |
| friendliness-index.pages.dev | 1440 | 11 | 387,318 | 992,374 |
| friendliness-index.pages.dev | 390 | 3 | 20,910 | 437,540 |
| friendliness-index.pages.dev | 320 | 3 | 20,910 | 437,547 |

Cold overview loads no raw blocks or NY detail. NYC detail requests no MA archive;
Boston detail requests no NY archive. Home archive bodies are 344,667 bytes at
1440 px and 4,526 bytes at each phone width. Largest observed range body:
159,805 bytes. Full per-view transfers are in the deployment receipt. Range body
counts use response Content-Length, including advertised lengths for responses;
CDP encoded totals cover completed responses including frontend/headers. The
browser report's `staticBytes` field sums advertised Content-Length only and
excludes chunked text without that header. These observed local client/network
measurements are not traffic forecasts, billed R2 operation counts or physical
phone/cellular performance.

The existing scoped archive cache rule includes `/ma/` and `/ny/`, with one-year
Edge TTL confirmed by the upload operator. Observed Browser Cache-Control is
`max-age=14400`; this differs from configured edge retention. Two pre-upload
cached detail 404s were purged by exact URL using supported Computer Use, then
both exact URLs and all publication checks passed. No bucket objects or MA cache
entries were deleted; no new grants, credentials, services or DNS/security changes
were made by this task.

The streamed full-hash verifier temporarily used independently verified public
address 104.21.50.250 because system DNS was intermittent, keeping hostname/SNI
and TLS validation. All staged/live Chrome runs used normal DNS, TLS and CORS,
without archive interception or address overrides.

## Rollback and evidence

Both existing rollback deployment manifests and sampled analytical payloads are
byte-verified unchanged and publicly accessible:
https://36133e09.friendliness-index.pages.dev (MA archive production), and
https://3c407db9.friendliness-index.pages.dev (loose-PNG fallback).
The MA source remains commit `0a3d795e6d4bb37f2b573dbdfc4947fc01e53e46`; its archive
SHA-256 remains `876b2af034895c8abd6fbf9a957beca5e3e47b9954f316dd1f5407fd5409b2e7`.
Frontend rollback does not require deleting the immutable NY objects.

Evidence under `qa-artifacts/continuous/`: `deployment-receipt.json`,
`public-endpoints-ui300.json`, `ui300-live/{results,pixel-comparison}.json`,
`ui300-staged-public/{results,pixel-comparison}.json`, `rollback-receipt.json`,
`final-package-audit-ui300.json`, `ui300-deploy.log` and `ui300-deployments.log`.
The follow-up QA/documentation commit is separate from the deployed source commit.

Reproduce live browser verification using the deployed source identity:

```powershell
$env:QA_COMMIT='f869e788854a51d74645bb7b888a01b15ef9b650'
node scripts/continuous-live-qa.cjs
```

## Historical preparation and approval record

The following preparation record is retained as history. Its pending statuses
are superseded by the verified release above.

# Continuous MA + NY publication — approved, endpoint checks pending

Publication was explicitly approved after review of the continuous map. The R2
browser uploader has a 300 MB per-file limit, so the original 352,685,199-byte
detail object is preserved locally and superseded by two lossless zoom partitions.
No new credentials, grants, paid services or authentication transports are needed.
The browser operator handles upload and approved scoped `/ny/` cache eligibility.
The deployment operator uses the existing authorized Pages CLI after endpoint QA.

## Exact revised candidate

Candidate: `build/ma-ny-continuous-ui300`; display identity `ead61093d03122c6`.
Both states share `/` on `maps.chrislentner.com` and `friendliness-index.pages.dev`.
There is no switcher or separate NY page. Tile addresses select MA, overview,
z13 detail, z14 detail or an immutable shared composite. Archive readers and raw
indexes are lazy. Analytical overlap prefers finite MA, including zero; display
overlap copies the first nontransparent MA tuple or NY without double opacity.
Scores, projections, all source datasets and MA rollback remain unchanged.

| Hosting item | Existing MA | Revised MA + NY | Increment |
| --- | ---: | ---: | ---: |
| Pages inputs including `_headers` | 441 | 2,734 | 2,293 |
| Served static assets | 440 | 2,733 | 2,293 |
| Staging bytes | 175,551,041 | 1,074,013,041 | 898,462,000 |
| R2 objects | 1 | 4 | 3 |
| R2 archive bytes | 147,249,624 | 708,394,643 | 561,145,019 |

Largest Pages asset: 1,106,773 bytes. All 2,607 float32 parts are preserved.
The revision adds 468 Pages bytes and 2,541 R2 bytes compared with the two-archive
continuous candidate. The 102 composites remain exactly 4,044,676 bytes, with all
PNG payloads unchanged. All archives are smaller than 300,000,000 bytes.
The existing MA object and `_headers` security/cache rules remain intact.

## Exact immutable upload objects

Bucket: `friendliness-index-rasters`. Use the existing `tiles.chrislentner.com`
public hostname. Files are staged with their exact object names under
`build/r2-upload/ny/b42279c259905289/`. Upload these three objects only, retaining
the original oversized detail archive locally without uploading it.
Configuration: `deploy/ny-archives-ui300.json`. Content type is PMTiles;
no external Content-Encoding. Use existing cache settings and the approved
scoped one-year Edge TTL. Verify effective public response headers afterwards.

| Native zoom | Key | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| 5–12 | `ny/b42279c259905289/e25d3229b7a63897-overview.pmtiles` | 208,457,279 | `e25d3229b7a6389736b96990f92d6deaeb0f9e2c8a97e4880106d0c1d32ac30e` |
| 13–13 | `ny/b42279c259905289/9575dd6e9a1a38dd-detail-z13.pmtiles` | 270,440,592 | `9575dd6e9a1a38dd38f3990a56e8cae95f759a8fd1d5845be777936481e7dbd1` |
| 14–14 | `ny/b42279c259905289/42203923f723a798-detail-z14.pmtiles` | 82,247,148 | `42203923f723a798824ae027acc6646da6b72bf9afce86621b3b480100f4ff0d` |

The Python repacker copies completed archive payloads directly. All 48,740 detail
addresses are disjoint by zoom and their union equals the original detail set.
Both Python and the official JavaScript 4.5.0 reader independently verify every
new payload hash against the original PNG inventory (10,224 z13; 38,516 z14).
The overview remains exactly the original 208,457,279-byte object. No scoring,
source acquisition, export, resampling or spatial partition is performed.

## Verification and execution

Local split/readers, staging and regression results are under
`qa-artifacts/ny/archives/ui300/` and `qa-artifacts/continuous/`. The new staging
report is `preparation-ui300.json`; browser comparison output is `browser-ui300/`.
The prior continuous evidence remains under `browser-final/` and is historical.
The revised local candidate passes 41 Python tests and 12 JS checks, all six
browser runs (19 views each), 57 pixel-identical comparisons, 43 raw-score fixtures
per viewport and all 2,734 final package hashes. Audit:
`final-package-audit-ui300.json`. Public endpoint/staged-live checks remain pending.

1. Receive the browser operator's upload result; do not operate Edge concurrently.
2. Run `scripts/verify-ny-public-endpoints.py` for exact full streamed size/hash,
   sample Range/206 bytes, stable ETag, exposed CORS headers from both existing
   frontend origins, no external encoding and edge cache HIT.
3. Run `scripts/continuous-live-qa.cjs --staged` with real public archives and
   frontend substitution on the two approved origins. This exercises browser CORS,
   archive zoom transitions and the revised staged frontend before cutover.
   Headless Chrome is used so it does not interfere with the operator's Edge.
4. Deploy only `build/ma-ny-continuous-ui300` to the existing `friendliness-index`
   Pages project via the existing CLI session, production branch `main`, explicitly
   recording the reviewed source commit. Repository branch remains `master`.
5. Run `scripts/continuous-live-qa.cjs` on both established origins at 1440x900,
   390x844 and 320x568. Verify Home framing, MA/NY seam pans, overview/z13/z14
   transitions, raw-score fixtures, partial archive reads, unchanged asset hashes,
   attribution, overlay, popup and two normal live-basemap views. Save the immutable
   deployment URL and final receipt. Phone-sized desktop viewports are not physical
   phones or cellular testing.

Keep MA live until the uploaded endpoints and staged-public checks pass. A failure
must be reported without disguising incomplete checks as a verified cutover.
No new credentials/grants/services or general network/security changes are permitted.
Pricing/usage is account-wide; measured object bytes and request counts are not a
promised monthly bill. See current [R2 pricing](https://developers.cloudflare.com/r2/pricing/).

## Preserved rollback

MA source commit `0a3d795e6d4bb37f2b573dbdfc4947fc01e53e46`, Pages deployment
`36133e09-c66d-45cf-a3ee-3b99dde26f47` at
https://36133e09.friendliness-index.pages.dev, and loose-PNG rollback
`3c407db9-427b-412f-a2c7-96ac23745cab` remain available.
The MA archive remains `build/archives/massachusetts-5124e42eb1483a75.pmtiles`,
147,249,624 bytes, SHA-256
`876b2af034895c8abd6fbf9a957beca5e3e47b9954f316dd1f5407fd5409b2e7`.
The original two-part NY config and both earlier continuous candidates are retained.
Frontend rollback does not require deleting R2 objects or changing DNS or security.
