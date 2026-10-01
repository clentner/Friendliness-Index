# Unpublished hosting preparation

No account, bucket, Worker, DNS record or site has been created. This directory
is a configuration handoff; it does not deploy anything.

Host frontend assets on a static HTTPS host. Store immutable `datasets/` content
in an object store (for example R2) behind a CDN. Prefer routing `/datasets/*`
under the same origin so the existing manifest works without CORS. An edge
Worker may provide that route/cache, but is not necessary if the host supports
an equivalent origin rule. XYZ PNG delivery does not require PMTiles or Range
requests. A later PMTiles migration must independently validate Range caching.

For a different data origin, replace `manifest.tile_url` with its complete HTTPS
template and configure the viewer's URL resolver accordingly before deployment;
the currently tested build uses relative, same-origin paths only. Adapt the
placeholder CORS policy to the exact frontend origin. Never place write keys in
the frontend. `deploy/_headers` is a static-host header template; copy it into
the staged frontend output if that host supports this convention.

Publication checklist:

1. Verify tests, source provenance, licensing/attribution, intended public access
   and basemap provider. Public OSM tiles have no SLA and prohibit bulk/offline
   download; choose a production provider with appropriate terms.
2. Upload a new dataset prefix, verify metadata checksum/raw score checksum and
   representative PNGs, then update `manifest.json` last. Keep prior dataset
   prefixes for rollback. Never overwrite content under an immutable ID.
3. Serve dataset assets with one-year immutable caching; revalidate the manifest
   and frontend. Supply correct `image/png`, JS, CSS and JSON content types.
4. Check HTTPS, mobile UI, visible attribution, gzip/Brotli for text assets,
   cache-hit behavior, coverage edges and storage/request/egress budgets.
5. Obtain authorization before publishing, provisioning or purchasing services.

Physical iPhone Safari / Android Chrome validation and a throttled cellular
network test remain release gates. Desktop headless results are not substitutes.
