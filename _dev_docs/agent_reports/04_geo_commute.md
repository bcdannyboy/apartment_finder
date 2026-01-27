# Geo/Commute Local-First Stack (2026-01-27)

## Geo Stack (geocoding + routing)
- **Geocoding (local-only):** Self-host **Pelias** as primary, with **Nominatim** as optional fallback. Both are OSM-based, cacheable, and avoid paid/remote APIs. Use **libpostal** normalization and candidate generation, then snap to **DataSF building footprints/parcels** for rooftop/parcel precision when confidence is low. (Aligns with architecture_components 1.8 and architecture_kickoff 6.1/6.4.)
- **Routing (local-only):**
  - **Transit:** **OpenTripPlanner (OTP)** with static GTFS + GTFS-RT (when allowed) for time-of-day commute scoring. (architecture_components 1.8, architecture_kickoff 6.2/6.5)
  - **Walk/Bike/Drive:** **Valhalla** for routes, matrices, and isochrones; **OSRM** optional for faster baseline routing when isochrones not needed. (architecture_components 1.8, apt_juror_4)
- **Spatial stack:** Postgres + **PostGIS** for joins, isochrones storage, and neighborhood/QoL overlays. (apt_judge, apt_juror_4)

## Data Sources + Licensing Constraints
- **OSM base data** for Pelias/Nominatim/Valhalla/OSRM (open data; ODbL attribution obligations).
- **DataSF layers (open data; local copy for runtime):**
  - Building footprints (ynuv-fyni), parcels (acdm-wktn), building permits (i98e-djp9), DBI complaints (gm2e-bten), notices of violation (nbtm-fbw5), 311 cases (vw6y-z8j6), neighborhoods (gfpk-269f), parks (3nje-yn2u), elevation contours (6d73-6c4f), slopes (s66h-h4vp). (sf_open_data_layers_2026-01-27)
- **Transit data (open data with constraints):**
  - **511 regional GTFS + GTFS-RT** requires API key, strict rate limits, and **non-commercial / no redistribution** license terms. (sf_transit_data_2026-01-27)
  - **SFMTA GTFS** (quarterly or when schedule changes), **BART GTFS + GTFS-RT**, **Caltrain GTFS** (as schedules change). Each has its own license and trademark restrictions; none are paid but all are revocable. (sf_transit_data_2026-01-27)

## Ingestion + Update Cadence
- **OSM extracts:** weekly (or daily if feasible) for Pelias/Valhalla/OSRM graph freshness; rebuild on a rolling schedule.
- **DataSF layers:**
  - **High-frequency:** 311 cases (multiple/hour, published daily), building permits (multiple/hour, published daily), parcels (daily), notices of violation (daily).
  - **Medium:** DBI complaints (weekly publish), building footprints (as-needed changes, published daily).
  - **Low/rare:** neighborhoods, parks, elevation contours, slope layers (as-needed or historical). (sf_open_data_layers_2026-01-27)
- **Transit:**
  - **511 regional static GTFS:** daily (use status=active); rebuild OTP graph when new feed lands. (sf_transit_data_2026-01-27)
  - **GTFS-RT:** poll ~20-30s if using 511/BART feeds; respect rate limits. (sf_transit_data_2026-01-27)
  - **Agency GTFS (SFMTA/BART/Caltrain):** update when schedule changes are announced; SFMTA at least quarterly. (sf_transit_data_2026-01-27)

## Caching + Precision Strategy
- **Geocode pipeline:** libpostal normalize -> variant generation -> Pelias/Nominatim -> snap to **building footprint or parcel centroid** when confidence is low -> store `geocode_confidence`, `precision` (rooftop/interpolated/parcel/zip), and `location_redaction` (exact/cross_streets/neighborhood/zip). (architecture_kickoff 6.4, apt_juror_4)
- **Commute caching:**
  - Cache key: `(origin_h3, anchor_id, mode, time_bucket)` with H3 at a conservative resolution for privacy and reuse. (architecture_kickoff 6.6)
  - **Precompute isochrones** for anchors/time buckets (weekday AM/PM, weekend). (architecture_components 1.8, architecture_kickoff 6.2/6.6)
  - TTLs: walk/bike **months**, transit **days**, GTFS-RT **hours**; store both scheduled and real-time variants, fallback to scheduled when RT missing. (architecture_kickoff 6.6, apt_juror_4)
- **Runtime policy:** no external API calls during query; all map layers and routing operate on local data stores (matches "no cloud dependency except Firecrawl/OpenAI").

## Conflicts with constraints
- **Paid / cloud services not allowed:** Mapbox (geocode/matrix/isochrone), Google Maps (geocode/routes), TravelTime, OpenCage, Geocode Earth, GraphHopper hosted APIs. These are mentioned in apt_judge and apt_juror_4 but **must be excluded** under the "no paid services except Firecrawl/OpenAI" rule. (architecture_kickoff constraint; apt_judge; apt_juror_4; geo_routing_policy_comparison_2026-01-27)
- **License risk:** 511 GTFS/GTFS-RT is open data but **non-commercial and no redistribution**; OK for local personal use, but incompatible with commercial distribution without written authorization. If commercial use is required, prefer agency-provided GTFS and avoid 511 RT or obtain permission. (sf_transit_data_2026-01-27)
