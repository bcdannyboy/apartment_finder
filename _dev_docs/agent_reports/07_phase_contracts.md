# Phase Contracts

## Phase 5 - Geo and Commute Enrichment

### Test summary
- Local-only geocoding and routing; Pelias primary with Nominatim fallback; no external paid APIs.
- OTP for transit; Valhalla for walk, bike, drive; engine selection enforced.
- Commute cache keys include origin_h3, anchor_id, mode, and time_bucket.
- Deterministic results for fixed inputs with verified cache usage.
- Geocode precision and confidence fields required and persisted.
- 511 GTFS stored locally only, not redistributed; GTFS updates trigger OTP graph rebuild and versioned activation.
- Detailed plan: _dev_docs/agent_reports/phase_tests_phase5.md
