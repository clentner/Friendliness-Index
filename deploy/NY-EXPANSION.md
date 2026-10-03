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
Final revised browser/package results must pass before deployment.

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
