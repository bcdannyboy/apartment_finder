# Merge Notes

## Conflicts across reports
- Paid services vs hard constraints: some juror/judge notes recommend Mapbox/Google geocoding, TravelTime/Mapbox matrices, OpenCage, and Twilio SMS, which violate the "only paid services: Firecrawl + OpenAI" rule.
- Search backend split: apt_judge mentions OpenSearch and a separate vector DB, while core docs use Postgres + pgvector.
- Connector extraction overlap: connector interface includes extract(snapshot) while a centralized Extraction Service is defined.
- Scheduler responsibility gap: kickoff discusses scheduler/queues but the component list omitted a named Scheduler/Workers module.
- Facts optional vs required: schema outline marked facts as optional while provenance-first requires field-level facts/evidence.
- Compliance mismatch: high-velocity portal crawling in some notes conflicts with manual-only restriction for major portals.
- Geo/routing ambiguity: Pelias vs Nominatim and Valhalla vs OSRM not resolved in core docs.

## Decisions made (enforced)
- Only paid services allowed: Firecrawl and OpenAI. All paid geo/routing/SMS services are excluded.
- Search stack: Postgres FTS + pgvector (no OpenSearch).
- Extraction centralized in Extraction Service; connectors only enumerate/fetch/check_status.
- Add Scheduler/Queue/Workers as an explicit component.
- Field-level facts and evidence are required (not optional).
- Manual-only sources enforced for restricted portals; policy gate blocks automation.
- Geo stack: Pelias primary, Nominatim optional fallback; OTP for transit; Valhalla for walk/bike/drive (OSRM optional).

## Conflicts resolved
- Removed paid geo/routing/SMS options from authoritative architecture; local-only geo/commute enforced.
- Standardized retrieval to Postgres FTS + pgvector.
- Clarified connector responsibilities vs Extraction Service.
- Explicitly added Scheduler/Queue/Workers to the component model.
- Made facts/evidence mandatory for all non-null fields.
- Reinforced manual-only list for restricted portals and blocked automation paths.

## Open questions
1) Queue system choice (Redis/RQ vs Celery vs Postgres-based queue).
2) Routing engine secondary option (run OSRM alongside Valhalla or Valhalla only).
3) UI scope (minimal vs full SPA).
4) Use of 511 GTFS feeds given licensing restrictions (local-only vs avoid 511 RT).
5) Object storage (filesystem vs MinIO).
6) Evidence storage shape (JSONB-only vs normalized FieldObservations table).
