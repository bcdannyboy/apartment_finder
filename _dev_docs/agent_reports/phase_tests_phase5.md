# Phase 5 Test Plan - Geo and Commute Enrichment

## Scope
- Validate geocoding, routing, and commute enrichment for Phase 5.
- Enforce local-only operation and licensing constraints.

## Non-negotiable constraints
- Local-only geocoding and routing; no external paid APIs.
- Pelias is the primary geocoder; Nominatim is the fallback.
- OTP handles transit routing; Valhalla handles walk, bike, drive.
- 511 GTFS is stored locally and never redistributed.

## Test data and fixtures
- Local Pelias index built from approved sources.
- Local Nominatim instance with matching coverage.
- Local OTP graph built from local 511 GTFS.
- Local Valhalla tiles covering the target area.
- Canonical address set covering rooftop, parcel, interpolated, locality, and POI cases.
- Canonical origin and destination pairs for each mode.

## Test categories and required checks

### 1) Local-only network isolation
- Block outbound network egress in test runtime.
- Assert no requests to external geocoding or routing endpoints.
- Allowlist only local hosts or container network addresses.

### 2) Geocoding primary and fallback behavior
- When Pelias returns valid results, Nominatim is not invoked.
- When Pelias returns empty or error, Nominatim is invoked once per request and the source is recorded.
- If both fail, return a typed error with no partial data.

### 3) Geocode precision and confidence fields
- Each geocode result includes `precision` and numeric `confidence`.
- `precision` is from a fixed enum set (rooftop, parcel, interpolated, centroid, locality, region).
- `confidence` is within the allowed range and stable for fixed inputs.
- Precision and confidence are preserved in outputs and caches.

### 4) Routing engine selection by mode
- Transit requests use OTP and include OTP metadata in the response.
- Walk, bike, and drive requests use Valhalla and include Valhalla metadata in the response.
- Engine selection is consistent for identical inputs and does not mix engines unless explicitly configured.

### 5) Commute cache key shape
- Cache key is stable, normalized, and includes origin_h3, anchor_id, mode, and time_bucket.
- origin_h3 uses the configured H3 resolution; anchor_id is canonical and stable.
- Cache key excludes raw address text, raw coordinates, and user identifiers.
- Cache key field order is canonical and validated by structured parsing.

### 6) Determinism and cache usage
- Repeat identical requests produce identical outputs within numeric tolerances.
- Second request hits cache and emits a cache hit signal.
- Any change in origin_h3, anchor_id, mode, or time_bucket forces a cache miss.

### 7) 511 GTFS licensing compliance
- GTFS files are stored only in local paths with restricted permissions.
- No API or export endpoint exposes raw GTFS or feed slices.
- Build artifacts and logs do not contain GTFS files or raw feed content.
- Copy or sync jobs are blocked unless the target is approved local storage.

### 8) GTFS update handling and OTP graph rebuild
- GTFS feed fingerprint changes trigger an OTP graph rebuild.
- The rebuilt graph version is activated and used for subsequent routing.
- Graph build failures are surfaced and handled with explicit behavior.

### 9) Valhalla tiles and profile versioning
- Valhalla uses only local tiles; missing tiles surface clear errors.
- Cost model or profile changes trigger cache invalidation per policy and update outputs.

### 10) Observability and auditability
- Logs and metrics include engine, source, fallback reason, cache hit or miss, and feed fingerprint.
- Outputs are traceable to geocode precision, confidence, and routing version.
