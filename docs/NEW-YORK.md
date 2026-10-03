# Continuous Massachusetts and New York map — final local revision

The final candidate is `build/ma-ny-continuous-final`, display dataset
`159c1e74953cb90e`. Both states appear on one map without a region switch.
Viewport tile addresses select only the relevant archive, and clicks select the
original analytical float32 block. Scores, scoring parameters, state datasets,
production and rollback artifacts are unchanged. No NY objects were uploaded.

## Final verified candidate

- 2,734 Pages upload inputs, 2,733 served assets, 1,074,012,573 bytes;
  increment over MA: 2,293 assets / 898,461,532 bytes. Largest asset: 1,106,773 bytes.
- The continuous revision adds 97 inputs / 3,278,050 bytes over the earlier
  switcher candidate. It reuses all 2,607 original float32 parts.
- 99 shared original tile addresses become deterministic composite PNGs;
  three low-zoom MA overview tiles bring the composite total to 102 /
  4,044,676 bytes. Each pixel copies the first nontransparent MA tuple or NY
  tuple, preserving alpha without source-over blending. One raster layer displays
  the result. Analytical overlap prefers finite MA values, including zero;
  MA NaN falls through to NY. Failures reject rather than masquerading as no-data.
- Readers and raw indexes are lazy. Cold overview loads no raw blocks or NY
  detail archive. Boston detail requests no NY archive; NYC detail requests no
  MA archive. The z12/z13 source transition is exercised on each phone width.
- All 41 Python regression tests and 8 JavaScript checks pass. Saved final
  browser runs cover 17 views at 1440x900, 390x844 and 320x568: 51 archive/reference
  screenshot pairs rechecked with zero differing pixels; 43 independently derived
  raw-score fixtures per width include finite zero, NaN, borders and outside
  coverage. No page errors, request failures or overflow; framing, Home, overlay,
  attribution and click popup checks pass. The 320 px overview was visually inspected.
- Final package audit rehashed every staged asset and both original dataset
  payload trees, matching the saved inventory and current frontend/builder sources.
  Audit: 3.250 seconds; final staging: 11.03 monitored seconds, 61,304,832 bytes
  peak working set. This reused completed data; no import/scoring/export rerun.

| Width | Cold archive ranges | Cold archive bodies | Cold static bodies | Cold encoded transfer | Home archive bodies |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1440 | 11 | 387,318 | 1,633,738 | 2,028,871 | 344,667 |
| 390 | 3 | 20,910 | 1,449,750 | 1,474,112 | 4,526 |
| 320 | 3 | 20,910 | 1,449,750 | 1,474,112 | 4,526 |

Body bytes and CDP encoded transfers are separate measurements. Archives use
Range/206 only through local URL interception, with basemap network requests
replaced locally. These are not live endpoint or cellular-network measurements.

Evidence: `qa-artifacts/continuous/preparation.json`,
`staging-final.resources.json`, `final-package-audit.json`,
`browser-final/results.json` and `browser-final/pixel-comparison.json`.
Reproduce with `scripts/prepare-continuous-site.py` (new output path required),
`scripts/continuous-query-fixtures.py`, `scripts/continuous-browser-qa.cjs` and
`scripts/compare-pmtiles-screenshots.py`. Preserve the current final candidate;
publication follows [the revised plan](../deploy/NY-EXPANSION.md) only after approval.

## Historical data-build and switcher evidence

The following record describes earlier candidates and checkpoints. Its switcher,
`/ny/` layout and 2,637-input counts are superseded by the final revision above.

# New York local expansion

Massachusetts production and rollback artifacts are unchanged. Nothing from this
build has been published. The metric, EPSG:32619 projection, 25 m lattice and
975 m scoring halo remain unchanged.

The local build and browser validation are complete. Publication awaits approval
of the [exact incremental hosting plan](../deploy/NY-EXPANSION.md), followed by
live Range/CORS/cache verification of the two new immutable objects.

The combined `build/ma-ny-pmtiles` bundle has **2,637 upload inputs /
1,070,734,523 bytes**, adding **2,196 served assets / 895,183,482 bytes** over MA.
It retains 439 MA served assets byte-for-byte and only adds the state switch to
MA's HTML. The largest asset is 1,106,773 bytes. Combined staging took 56.13
seconds at 25,153,536 bytes peak RAM. All 12 navigation views across three widths
passed, with correct active-region labels, correct archives, no overflow/errors,
and Range-only loading. Both source staging directories remain unchanged.

The local inventory at 2026-10-03 20:39:58 UTC contains 45,038,266,797 unique
file bytes across dated sources, parent, caches, exports, staging and preserved
repair backups, with 292,965,064,704 bytes disk free. Hard links count once;
this includes shared MA source files and a MA staging copy and is not all NY
incremental storage or allocated disk clusters. Exact hosting deltas are measured
separately. Evidence: `build-resources.json`, `combined-site.json` and
`combined-browser/results.json` under `qa-artifacts/ny`.

## Archive browser validation

The exact staged NY frontend passed six local Edge/Playwright runs: loose PNG
and two-archive delivery at 1440×900, 390×844 and 320×568. All **63 screenshot
pairs match exactly**, with zero differing pixels. Each pair covers the full
state overview, both sides of the z12/z13 archive boundary, 15 covered urban,
island and remote locations, and three outside-coverage locations. Home, the
score toggle, coverage labels, attribution and no-overflow checks passed; there
were no page/console errors, failed requests or external network requests.

| Viewport width | Cold archive Range requests | Cold archive body bytes | Whole tour Range requests | Whole tour archive body bytes | Largest Range body |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1440 | 11 | 493,308 | 275 | 12,150,130 | 209,911 |
| 390 | 7 | 133,879 | 155 | 6,998,612 | 209,911 |
| 320 | 5 | 48,191 | 116 | 4,647,087 | 175,721 |

Every archive GET used a byte Range and returned 206. No whole archive was
downloaded. The cold state view requests only the overview object. Actual zoom
boundary transitions requested the expected overview/detail object. Sparse
tiles were transparent, including outside NY and off-network areas. HTTP tests
also cover suffix/open-ended ranges, invalid 416 responses, HEAD and rejection
of a full archive GET.

The existing animated Home return fetched intermediate views: 5,825,887,
4,414,721 and 2,437,786 archive body bytes respectively. It is not a zero-byte
warm cache test. The report records server-completed response bodies separately
from browser CDP encoded transfer (including frontend assets/headers); animated
or canceled loads and the local request interceptor make these distinct measures.
Cold total browser encoded transfers were 1,804,770 / 1,443,588 / 1,357,024 bytes.
These are local observed bytes, not cellular timings or a future traffic bill.

Evidence: `qa-artifacts/ny/browser/results.json`, `pixel-comparison.json` and
126 captures. The production HTTPS archive URLs were intercepted and forwarded
to a loopback Range server. CORS exposure was supplied locally. Live NY object
Range, CORS, ETag, TLS and edge-cache verification remains pending authorized
upload; no physical phone or cellular-network claim is made.

NY archive staging contains **2,196 inputs / 895,182,727 bytes**, including all
2,181 unchanged raw float32 parts / 892,416,000 bytes. It omits 52,433 loose PNG
objects and verifies all 54,629 display-source files remain unchanged. Staging
took 323.86 seconds at 50,393,088 bytes peak RAM, primarily complete source and
output hashing. The 39 regression tests passed in 7.212 seconds after integration.

## Hosting comparison inputs (verified 2026-10-03)

The [Cloudflare cache documentation](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/#cacheable-size-limits)
still sets a 512 MB cacheable-object limit for Free/Pro/Business.
[Pages Free](https://developers.cloudflare.com/pages/platform/limits/) allows
20,000 files per site and 25 MiB per asset. Decide whether NY requires regional
archives from the measured PNG/archive bytes, and verify range-only browser
transfers before proposing publication.

[R2 Standard pricing](https://developers.cloudflare.com/r2/pricing/) is
$0.015/GB-month, $4.50/million Class A operations and $0.36/million Class B
operations, with no egress fee. Monthly free allowances are 10 GB-month,
one million Class A and ten million Class B operations. Billing rounds usage
up to whole billing units; actual incremental charges depend on account-wide
usage and traffic. A publication proposal must distinguish exact added objects,
bytes and measured requests from a conditional monthly cost estimate. No NY
hosting footprint exists yet, and no account/service setting has changed.

The generalized archive staging command now accepts explicit configuration and
report paths, derives PNG/raw counts from the export, and rejects an archive
larger than 512,000,000 bytes. Its MA regression completed in 85.22 seconds at
24,297,472 bytes peak RAM. The separate `build/ma-staging-regression-ny` copy
reproduces **441 upload inputs / 175,551,041 bytes**; all 426 raw parts and all
9,916 original source-export files were hash-verified unchanged. Evidence:
`qa-artifacts/ny/ma-staging-regression.json`. This local check changed no live
assets and did not replace the existing production staging or rollback files.

## Completed data export and display variant

The original worker/session 57595 completed successfully and released its lock.
The base export has **52,425 PNGs / 560,884,874 bytes**, all distinct payloads;
even before PMTiles directory overhead, one archive would exceed the conservative
512,000,000-byte cache ceiling. Use bounded archives, not one oversized object.
Base export totals are **54,618 files / 1,456,877,602 bytes**, largest 1,105,986
bytes. Export took 3,181.05 monitored seconds (53.0 minutes), at 136,519,680
bytes peak RAM (130.2 MiB): assembly 1,046.250 seconds, raw writing 15.920 seconds,
and tile rendering 2,115.480 seconds. The loose file count exceeds Pages limits.

Full verification passed in 139.32 monitored seconds at 138,870,784 bytes peak
RAM. All 50,866,538 finite analytical cell centers have a present z14 tile;
zero required tiles are missing. There are 39,303,274 finite-zero cells, distinct
from NaN/no-data. Raw parts contain 892,416,000 exact bytes; a level-6 gzip trial
measured 57,146,547 bytes, but delivery remains the original float32 format.
Evidence: `qa-artifacts/ny/verification.json` and the stage resource reports.

### Measured mobile overview defects and separate display fix

A real local browser layout probe found that the MA-derived minimum camera zoom
clips NY at 320 px (bounds project from x=-35.38 to 327.38), and z7-minimum raster
coverage yields **zero** overview tile requests at both phone widths. Lowering
the camera minimum alone frames NY correctly but still requests no raster tiles.
Adding z5/z6 overviews gives 4 requests at 320 px and 6 at 390 px, with NY fitting
the intended x=24..268 / x=24..338 padding. The probe used transparent synthetic
tiles to isolate layout/source behavior; actual raster browser QA is recorded below.
It also exposed URL-escaped `{z}/{x}/{y}` placeholders in the loose-viewer URL.
Evidence: `overview-layout-probe.json` and `overview-layout-fix-probe.json`.

`web/app.js` now preserves literal tile placeholders and accepts the optional
`min_view_zoom` field while retaining the existing fallback for MA. The completed
base export is preserved. `scripts/extend-region-overviews.py` created the separate
`build/new-york-display` variant in 40.10 monitored seconds, at 53,002,240 bytes
peak RAM. Its 54,607 original PNG/raw payloads are unchanged hard links, with
separate metadata/client files. Eight new z5/z6 overview PNGs add **148,634 bytes**.
Display totals are **52,433 PNGs**, **54,629 files / 1,457,314,169 bytes** before
archive staging. The same dataset `b42279c259905289` and score hash
`e9755f7af8419cb2b962a94ebb78ec12009d1b167a74b74c8e4ea147160faf74` are retained;
display derivation provenance is recorded separately. No metric was recalculated.

Display verification passed in 326.73 monitored seconds at 137,637,888 bytes
peak RAM. An independent ordinary-file pixel verifier checked 1,310,720 pixels
at 20 locations: 16 exact RGBA matches and four correctly absent no-data tiles.
It completed in 2.01 monitored seconds at 100,806,656 bytes peak RAM. Evidence:
`display-verification.json`, `pixel-reference.json` and their resource receipts.

`package-region-archives.py` built z5–12 overview and z13–14 detail archives in
55.12 monitored seconds at 112,996,352 bytes peak RAM. Their exact sizes are
**208,457,279** and **352,685,199 bytes**; their payloads are 208,444,975 and
352,588,533 bytes. Both Python and the independent official JavaScript 4.5.0
reader checked every one of the 52,433 PNG payloads byte-for-byte. The client
routes tile zooms to the appropriate reader while preserving one raster source.
Exact immutable keys and complete SHA-256 hashes are in `deploy/ny-archives.json`
and the [publication plan](../deploy/NY-EXPANSION.md). Nothing is published.

The first packaging attempt stopped at an overly strict overview-only check
for exact native zero-blue RGBA after overview resampling. The corrected check
requires transparency in every part and exact native zero-blue in the detail
part. The failed temporary archive is preserved under `qa-artifacts/ny/archives`;
all source PNGs and analytical values are unchanged.

The access audit passed in 56.408 seconds (57.14 monitored), at 98,680,832 bytes
peak RAM. Four legacy acquisition/access candidates were found; none affect the
retained graph. Independent seams passed in 58.368 seconds (60.14 monitored),
at 179,113,984 bytes peak RAM: 204 seam query points, demonstrated cross-border
contributions from CT/MA/VT/NJ/PA/Ontario/Quebec, and **171 actual published MA
float32 overlap cells matched exactly**. Evidence: `access-audit.json` and
`seams.json` under `qa-artifacts/ny`.

Worker 21456 / session 57595 completed successfully and released its lock,
reusing 17 representative jobs. Preserve its signature-bound checkpoints and
all repair backups. The dense analytical rectangle is 2,136,372,000 bytes;
bounded file reads prevent that allocation from becoming resident RAM.

Full scoring completed at approximately 2026-10-03 19:16 UTC: 36,250 newly
completed jobs plus 17 reused samples, all 36,267 planned jobs. Internal time
was 1,876.581 seconds; monitored time was **1,878.24 seconds (31.3 minutes)**.
Peak working set was **180,588,544 bytes (172.2 MiB)**; minimum system RAM
headroom was 2,460,663,808 bytes, and minimum free disk 297,627,598,848 bytes.
No resource guard tripped and the scorer exited successfully. Leave session
57595 running when returning a parent checkpoint.

The full summary passed: median job 0.037174 seconds, p95 0.094647 seconds,
maximum 15.871718 seconds; 59,004 maximum halo vertices and 8,267 maximum POIs.
Total measured job loading was 557.398 seconds and scoring/checkpoint work
1,272.158 seconds (including reused samples). The recorded `score_seconds`
includes NPY writing, hashing and rename, not just the metric kernel.
Of 227,630,128 inside-state cells,
50,866,538 are reachable; 4,874 jobs have no reachable cell. Reading/summarizing
36,267 small JSON checkpoint files added **276.61 seconds**, peaking at
117,661,696 bytes RAM. This is a measured small-file metadata overhead, separate
from scoring; retain resumability while considering a consolidated summary or
bounded concurrent reader for future runs. Evidence: `scoring-summary.json`
and `ny-scoring-summary-1.resources.json` under `qa-artifacts/ny`.

At 2026-10-03 19:21:30 UTC, the same worker had started `ny-export-1.log`, child
PID 28780. At 17.04 export seconds, peak RAM was 107,155,456 bytes (102.2 MiB),
the 2,136,372,000-byte raster had been allocated, disk free was 295,488,188,416
bytes, and no guard had tripped. Export assembly/rendering and verification
remain in progress; actual PNG/archive sizes and hosting impact are not yet
available. The worker automatically verifies the completed export, then stops
before archive packaging/publication.

By 19:41 UTC, assembly/raw writing had completed and the export was rendering
checksummed z14 tile columns (3,086 tiles at the latest x=4620 checkpoint).
The dataset ID is `b42279c259905289`. The completed raw directory contains
**2,181 float32 parts / 892,416,000 bytes**, with largest part 409,600 bytes;
final verification will check every value and checksum against the raster.
Export peak working set at that checkpoint was 117,870,592 bytes (112.4 MiB).
The verification command also independently transforms every finite cell center
to require a corresponding finest-level PNG; it does not reuse the exporter's
candidate envelopes. This checks sparse-export coverage across the entire state.

The local integration draft is `deploy/NY-EXPANSION.md`: preserve MA at `/`,
add NY at `/ny/` on the existing origins, and use new immutable R2 keys. The
new `scripts/prepare-multi-region-site.py` will stage and inventory the combined
directory only after NY archive staging exists. It preserves all MA app/data
assets; the later discovery requirement adds only a region switch and stylesheet
reference to MA's HTML, plus NY-specific cache rules. Neither script nor draft
publishes anything; exact combined totals and range QA remain pending.

Latest parent checkpoint, 2026-10-03 **19:49:57 UTC**: worker 21456/session
57595 and exporter 28780 are healthy, still on `ny-export-1`. Highest-resolution
rendering reached **15,957 tiles** at completed x=4750. Export elapsed is
1,724.83 seconds (28.7 minutes); peak working set 121,978,880 bytes (116.3 MiB),
minimum system available RAM 2,297,794,560 bytes, and current free disk
296,405,073,920 bytes. No guard tripped. Keep the worker running into its queued
verification. Final PNG count/bytes, archive size and browser Range QA remain
pending; no NY files have been published. Local packaging imports, PMTiles JS
4.5.0, Playwright 1.58.2 and installed Edge were checked available without any
installation or credential changes.

The user subsequently requested discoverable NY coverage. The combined bundle
will have a persistent "Massachusetts / New York State" switch on both maps,
preserving MA's viewer logic, manifest, raw data and archive URL. Its 439 other
served assets must remain byte-identical. `web/region-navigation.css` provides
the shared compact control. `scripts/combined-region-browser-qa.cjs` exercises
actual MA -> NY -> MA navigation at desktop and two phone widths using local
Range endpoints. These staged-integration checks await the completed NY export.

### Representative benchmark results

Worker 21456 (session 57595) reused the completed graph after 43.12 seconds of
source/proof validation; no source pass or graph index was rebuilt. All 39 tests
passed again. All 17 representative scoring jobs finished in 20.811 seconds
(22.06 monitored), at 164,339,712 bytes peak RAM (156.7 MiB). Evidence is in
`qa-artifacts/ny/sample-summary.json`, per-job checkpoints and
`ny-samples-1.resources.json`.

| Representative 2 km job | Halo vertices | Halo POIs | Job seconds |
| --- | ---: | ---: | ---: |
| Midtown | 49,203 | 6,982 | 7.519 |
| Brooklyn | 42,767 | 2,784 | 3.493 |
| Hempstead | 23,596 | 418 | 0.889 |
| Montauk | 7,302 | 101 | 0.238 |
| Fishers Island | 2,930 | 13 | 0.083 |
| Adirondack wilderness | 224 | 0 | 0.048 |

Midtown spent 1.098 seconds loading and 6.420 seconds scoring/checkpointing. This demonstrates
substantial density-driven job skew while staying comfortably within memory
budgets. The intentionally dense-biased sample mean must not be extrapolated
to the full state. Access, independent seams/foreign contributions and exact
MA overlap passed before the 36,267-job statewide run.

### Verified relation repair

Both blocked POIs now have complete, independently decoded geometry from the
verified same-date US parent. A checksummed, resumable 8,391,107-byte block index
was built in 387.87 monitored seconds at 109,432,832 bytes peak RAM. The targeted
120,411-byte extract contains 12,494 nodes, 472 unique ways and both relations;
all node/way/relation references are present and imported versions match.
The independent proof took 174.42 seconds at 168,054,784 bytes peak RAM.

The full Torrey C Brown Rail Trail envelope is at least 218,598 m from NY's
required support; the full Connecticut River Byway envelope is at least 55,474 m
away. Their exact original-rule representative points are also outside support.
This is complete-geometry evidence, not inference from partial bounds or names.
Proof: `data/ny-20261001/relation-completion.json` and its checksummed PBF.

All 39 tests passed, including nested-member closure, missing nodes, changed
versions/bounds, proof tampering, protected graph writes and a deliberately
misleading partial remote geometry with a complete member inside NY. The repair
backs up the completed database/metadata in `qa-artifacts/ny/before-relation-repair/`,
adds 304 unique missing member bounds, preserves all ten file checkpoints, and
updates completeness metadata. A SQLite authorizer prohibits writes to graph,
POI and other source tables. The full post-repair integrity scan returned `ok`;
repair took 191.46 monitored seconds at 177,053,696 bytes peak RAM. Source loading now rejects unresolved
relations and verifies the completion proof and extract checksums.
One replacement worker is running in session 57595, with logs in
`worker-relations-resumed.log`. It revalidates the completed source and runs
benchmarks/access/seams before full scoring; the 1,100 MiB import guard and
32 MiB coordinate-cache cap are unchanged. No source re-import is required.

### Previous completeness stop

At 2026-10-03 18:22 UTC, session 26147 exited 1 and worker 2680/importer 18600
were gone; the worker lock was released. The importer itself finished normally
in 1,495.34 monitored seconds (1,494.087 internal seconds), with peak working
set 203,726,848 bytes (194.3 MiB), minimum system RAM headroom 2,326,052,864
bytes and minimum free disk 303,715,373,056 bytes. No resource guard tripped.
Quebec completed in 546.891 seconds, followed by the Sound supplement in
0.141 seconds. Final graph/index construction took approximately 262 seconds.
All ten source passes are committed. SQLite is 5,454,217,216 bytes with
19,537,679 vertices, 20,438,943 edges and 136,931 POIs.

The next correctness gate stopped that chain because two POI relations had
missing member bounds. No NY scoring or export had started at that checkpoint. Read-only
diagnosis is in `qa-artifacts/ny/unresolved-relations.json`:

| Relation | Dated source identification | Missing ways | Known geometry only |
| --- | --- | ---: | --- |
| 4233353 v18 | Torrey C Brown Rail Trail; Maryland Park Service; selected by `leisure=park` | 59 of 62 | [-76.6980066,39.602818,-76.6203632,39.721035] |
| 13058969 v62 | Connecticut River Byway (NH); selected by `tourism=attraction` | 248 of 416 | [-72.4544555,42.7267,-71.18045,45.2524032] |

Those partial bounds did not establish the complete representative coordinates.
The completed repair above used the verified same-date national parent and the
original POI representative/support rule; the gate was not waived. It preserved
the database and source checkpoints without a source re-import. Samples, access
audit and seams subsequently passed.

### Ontario memory fix completion

Ontario completed in **644.011 seconds** on the resumed pass, at 685.1 seconds
total resumed-import elapsed. Its file checkpoint is committed and SQLite is
3,245,596,672 bytes. Peak importer working set through this transition was
203,726,848 bytes (194.3 MiB), versus the unchanged 1,100 MiB guard. The bounded
coordinate cache ended at 33,459,040 resident bytes with 697,724 page misses and
2,787,811 hits. Its 91,445,688,864 logical read bytes include OS-cached reads.

The same worker (2680 / importer 18600 / session 26147) proceeded directly to
Quebec. At 720.6 resumed seconds, it had written 128 million Quebec coordinate
records, working set was 156,803,072 bytes, and free disk was 305,922,392,064
bytes. No guard had tripped; no second build process was started. Quebec,
supplement import, relation completion and final indexes must finish before
this can be called a completed graph build. `scripts/report-ny-build.py`
collects stage attempts and file inventories without changing build inputs;
hard-linked file identities are counted once in its aggregate.

At 2026-10-03 17:34 UTC, shell execution was verified working despite desktop
disconnection callbacks. Session 73507 exited with code 1; worker 29624 and
importer 18744 are gone, and the worker lock is absent. Only the preserved MA
preview Python process (15052) remained. This stopped attempt is preserved.

The Ontario pass hit the unchanged 1,100 MiB working-set guard after 4,483.62
seconds total import elapsed: peak 1,153,613,824 bytes (1,100.17 MiB). The seven
completed US-source checkpoints remain committed. Ontario's last cumulative
scan counter was 24.3 million ways; its disk location index is 2,350,287,712
bytes. System available RAM never fell below 1,106,251,776 bytes during this
attempt, so the stop was the per-process working-set guard, not the global RAM
guard. Free disk at stop was 311,388,286,976 bytes.

Read-only attribution isolated the coordinate file mapping as the dominant
resident allocation. At one million Ontario ways (15,149,273 references),
794,304,512 of the 842,231,808 working-set bytes belonged to that mapping;
private resident pages occupied 31,088,640 bytes. Closing the mapping reduced
the working set to 38,326,272 bytes. The native Windows mapping can also retain
its file handle until process exit. Evidence: `mapped-location-probe.log` and
its resources JSON under `qa-artifacts/ny`.

`pilot/locations.py` replaces this unbounded mapping with ordinary file reads,
8,192-record pages and a 256-page (32 MiB) LRU cache. A compact page fence array
supports exact node lookup. Way tags, access and existing versions are checked
before fetching coordinates. Required untagged relation nodes use the same
cache, eliminating the remaining global-ID bitset prepass. Complete way
geometry and the original support/segment intersection tests are preserved,
including crossings with both endpoints outside the core.

All 146,892,982 Ontario coordinate records were compared byte-for-byte against
the original PBF before reusing its native cache via a hard link. This took
42.09 monitored seconds at 57,888,768 bytes peak working set. Source and payload
checksums are recorded in `ontario-coordinate-equivalence.json`. The old cache
remains intact. Native-versus-paged fixture tests agree exactly on graph tables,
POIs, relation bounds, access barriers and metric scores. The separate real-way
probe passed all ten rolling hashes through one million ways / 15,149,273 node
references. Peak working set fell from 861,233,152 to 103,088,128 bytes (821 to
98 MiB, an 88% reduction). Workload time increased from 86.77 to 138.58 seconds;
this unfiltered probe performs every lookup, whereas the importer now filters
before lookup. Cache residency stayed at 33,554,432 bytes with no location file
mapping. Logical read traffic was 32,821,558,912 bytes, including OS-cached reads;
it is not a physical disk throughput measurement. The full evidence is in
`location-memory-comparison.json`.

Before recovery, the database, hot journal and import identity were copied to
`qa-artifacts/ny/before-memory-fix/` with SHA-256 checksums. SQLite performed normal
journal recovery; `quick_check` returned `ok`. All seven completed US-source
checkpoints and the immutable import identity match (`checkpoint-recovery.json`).
No completed source is rebuilt. `continue_ny_build.py --resume-import` skips
source re-registration, preserves previous stage logs, retains the 1,100 MiB
guard and rechecks partial export state on each resource retry.

At 2026-10-03 17:57 UTC the replacement worker (PID 2680, session 26147)
was active with importer PID 18600. All 34 tests passed in 6.216 seconds
(`final-tests-2.log`). The importer was validating immutable input checksums;
its first 37 seconds peaked at 120,053,760 bytes. Progress and resource records
are `worker-status.json`, `worker-resumed.log`, `ny-import-2.log` and
`ny-import-2.resources.json`. Do not start another worker while this lock owner
is alive. Samples, access audit, seams, full scoring and local export follow
only when the import and relation-completeness gates pass.
Source validation subsequently passed; the log explicitly reused all seven US
checkpoints and began Ontario at 41.1 seconds of the resumed invocation.

On 2026-10-03, the national-parent extraction finished in 1,267.27 seconds
(1,268.51 seconds monitored), peak working set 186,912,768 bytes. Its coordinate
pass covered 1,599,128,261 nodes in 437.24 seconds; national way-reference
matching was the dominant remaining cost. The accepted supplemental PBF is
208,592 bytes, containing 23,503 nodes, 1,752 complete ways and zero selected
POI relations. SHA-256:
`47e73c06d79062175b984d40734a66288db7fa0d65e8dbe5e7c0fb0870572cb1`.

Independent reference verification and the geographic audit passed. The audit
found no mapped nodes, walking ways or selected POIs inside the three original
missing polygons; retained context includes 218 walking ways, 12 coastline ways
and 10 POIs. This is dated OSM evidence, not a claim about unmapped accessibility.
The combined source check then passed in 27.30 seconds: zero missing support
area, matching snapshot timestamps, verified PBF hashes and all 17 sample points
covered. `source-check-initial.json` preserves the original failed check.
Full scoring, export, seam validation and archive/browser measurements remain
pending.

The first graph-source checkpoint (New York) subsequently completed in
2,858.70 seconds, at 2,999.5 seconds total import elapsed. SQLite occupied
3,210,698,752 bytes before neighboring-source passes and finalization. The last
walking-way commit counter before this checkpoint was 1,670,000. The same worker
continued directly into Massachusetts boundary context without a guard trip;
this is a source-pass milestone, not a completed graph import.

All seven primary US graph-source passes are now checkpointed. Measured pass
times in seconds: NY 2,858.70; MA 338.08; CT 202.67; VT 53.03; NJ 248.93;
PA 434.43; RI 33.27. SQLite occupied 3,238,854,656 bytes after RI. Ontario is
the remaining interrupted source; its disk location index is 2,350,287,712 bytes,
versus NY's 908,662,656 bytes. At 4,425 seconds total import elapsed, peak working set was
1,032,146,944 bytes and no resource guard had tripped. Quebec, the supplemental
extract, relation completion and index finalization still remain. These figures
must not be labeled completed-import or scoring/export measurements.

The Overpass failure is now being worked around with the authoritative dated
Geofabrik US parent, not by excluding the gaps. `data/ny-parent/us-261001.osm.pbf`
is fully downloaded and verified: 12,179,450,407 bytes, MD5
`d71586afe402cc5ae705baa7e718a329`, SHA-256
`699ae5b257e7b0d06c9b3bb66e4196257001844aca258e14dd75531cda5161e1`.
Its header matches the existing `2026-10-01T20:22:06Z` snapshot. A bounded 16 MiB
probe estimated 25.6 minutes before download; actual acquisition/checksumming
took 643.43 seconds at 29,605,888 bytes peak working set. Free disk afterwards
was approximately 320.4 GB.

The coordinate-only block reader scanned all 56,791,416 cached NY nodes in
14.625 seconds, with a monitored peak of 53,571,584 bytes. The per-node Python
callback comparison exceeded its 180-second guard. Two subsequent gap-selection
attempts exposed native global-ID bitset memory growth and stopped at the
400 MiB guard. The final extractor uses sorted ID arrays, bounded block-wise
reference joins and file-offset selection; original objects are independently
decoded/copied with pyosmium. It does not create a national node-location index.
The pinned protobuf dependency is recorded in `requirements-source-audit.txt`.

The cached-NY gap extraction passed in 44.90 seconds (45.07 seconds monitored),
with peak working set 124,264,448 bytes: 11,380 nodes, 946 complete ways, zero
selected POI relations and a 104,852-byte PBF. Its independent audit found no
mapped nodes, roads or POIs inside the missing polygons in this NY-only input;
this does not prove completeness of the missing neighboring source context.

The first national scan stopped after 285.62 seconds when system-wide available
RAM dropped below 384 MiB; its own peak working set was only 120,492,032 bytes.
No other application was stopped. Coordinate selection now writes checksummed
block-offset checkpoints every 2,000 blocks, allowing a safe resource retry.
All 29 tests passed in 3.282 seconds, including independent native-reader
comparison, nested relation completion, exact block-resume selection, and NY
tile-candidate envelopes. See `qa-artifacts/ny/final-tests-1.log`.

The old `continue_ny_parent.py` chain has exited. The single active replacement
is `scripts/continue_ny_build.py`; inspect `qa-artifacts/ny/worker-status.json`,
`worker.lock` and `worker.log` before doing anything. It waits for sustained RAM
headroom before each stage, then guards the child process's working set, system
RAM, elapsed time and free disk. It resumes selection/import/scoring/export
checkpoints and stops at any failed data gate. After parent extraction it runs
independent audit, registration and completeness checks, then graph import,
representative scoring/access/seam checks, full scoring, export and verification.
Archive packaging and browser/hosting-impact review remain separate. The worker
contains no publication commands. Do not launch a duplicate.

## Verified inputs and sizing

Nine dated Geofabrik extracts total 3,828,233,518 bytes: NY, MA, CT, VT, NJ, PA,
RI, Ontario and Quebec. Five files reuse checksum-verified immutable MA cache
files through hard links. Every PBF has replication timestamp
`2026-10-01T20:22:06Z`; provider MD5 and local SHA-256 were checked. Acquisition
took 229.78 seconds with 32,980,992 bytes peak working set. The NY administrative
boundary was requested at that same historical timestamp.

The plan includes NYC, Long Island, Fishers Island, northern border communities
and remote Adirondack samples. All 17 representative coordinates are inside the
boundary. It contains 36,267 absolute 2 km jobs, versus MA's 7,197. The enclosing
20,300 by 26,310 float32 raster requires 2,136,372,000 bytes. Its rectangular
zoom 7–14 pyramid has 137,750 addresses, including 103,012 at zoom 14; these are
upper bounds, not measured nontransparent export counts.

Scalar job geometry planning measured 28.059 seconds. Batching intersections by
row produced the same 36,267 jobs in 0.514 seconds, including boundary loading.

## Original source completeness gap - resolved by dated-parent context

The nine provider polygons leave 32,855,723.194 square meters of the required
1,025 m support buffer uncovered. Three gaps are in Long Island Sound and near
Fishers Island. This was a real failed gate, not a claim that OSM lacks mapped
features there. The independently verified parent supplement now closes it.

`scripts/acquire_ny_gaps.py` prepares dated supplementary Overpass metric extracts
with complete referenced members, checksums and category provenance. Responses
must be complete before they enter `sources.json`. Queries retain all highway
ways, barrier nodes and POI-category keys within expanded gap bounding boxes.
As with the original pilot, bounding-box selection does not prove retention of
arbitrary long segments whose endpoints are both outside the box. The neighboring
complete-way PBFs remain the primary crossing-segment source; this limitation
must be considered in the final completeness audit.

On execution recovery, both attempted public endpoints returned HTTP 504.
The primary endpoint also failed a small historical Fishers Island count query:
`Dispatcher_Client::request_read_and_idx::timeout. The server is probably too busy
to handle your request.` A direct request to the documented current mirror also
timed out. No partial response was accepted. Logs and the original missing-area
GeoJSON are retained in `qa-artifacts/ny/`.

## Initial recovery checkpoint (historical)

Uncommitted changes include bounded raster mappings, checksummed/resumable PNG
export, explicit archive staging beyond Pages' loose-file limit, disk headroom
monitoring, per-source import timing/checkpoints, and generalized verification
and access-audit commands. At initial recovery, NY seam/foreign-destination/MA-
overlap validation had not yet run against real NY scores; it has since passed.

After execution recovery, all 25 regression tests passed in 2.786 seconds, logged
in `qa-artifacts/ny/unit-tests-recovered.txt`. They include the existing 22 tests
and new bounded-raster, resume/corruption, and island/hole checks. The network
supplement subsequently passed its independent audit. Full export and browser
changes still need end-to-end validation.

The previous connection failure left no active NY job or import checkpoint. On
recovery, the only pre-existing Python process was PID 15052 serving the preserved
MA preview on loopback port 8765. Do not terminate it or overwrite MA output.

## Reuse and publication handoff

Use the existing Python environment with `PYTHONPATH=.;.venv/Lib/site-packages;.tools/protobuf`
and its actual base interpreter when using the Windows resource monitor.

1. The original build worker completed and released its lock. Inspect current
   processes before any retry; do not duplicate healthy work. All dated sources,
   national parent, completeness proof, graph, scores and exports are cached.
2. Source completeness, relation closure, 39 tests, access audit, 204 seam points
   and 171 exact MA overlap cells have passed. Do not re-import or repeat the
   national download. Preserve both repair backups and all MA rollback files.
3. Keep the original `build/new-york`, separate `build/new-york-display`, scoring
   signature and rollback data intact. Derived archive views use hard links;
   never edit a linked PNG/raw payload in place.
4. Reuse the two verified archives and exact configuration in
   `deploy/ny-archives.json`. Staging commands refuse to replace an existing
   output directory. Use a new output path for a future revision.
5. Read the measured browser and staging receipts plus
   `deploy/NY-EXPANSION.md` before publication. Local intercepted Range/CORS QA
   does not establish behavior of unpublished public objects.
6. Obtain explicit approval before uploading NY assets or changing the live
   frontend. Then verify real Range, CORS and edge-cache behavior for both exact
   URLs before deploying the reviewed combined bundle to the existing project.
