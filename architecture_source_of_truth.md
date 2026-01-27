# Apartment Finder Source of Truth Architecture

## Constraints (hard)
- Local-first system; Docker OK.
- Only paid services: Firecrawl and OpenAI.
- Strict compliance gating: only crawl sources marked crawl_allowed; restricted portals are manual-only unless licensed.
- Provenance-first: immutable snapshots and field-level evidence/confidence required for all non-null fields.
- Python is the core implementation language.

## Core components (authoritative)
1) Source Registry and Policy Gate
- Stores source policies, robots/ToS summaries, allowed operations, and rate limits.
- Blocks any automation unless policy_status == crawl_allowed.
- Allows ImportTask only for manual_only sources.

2) Acquisition Orchestrator
- Plans searches and sweep grids and generates Search/Map/Crawl/Scrape/Import tasks.
- Enforces per-domain budgets and cadence.

3) Scheduler / Queue / Workers
- Runs per-domain queues with politeness limits.
- Applies adaptive cadence, retries, and backoff.
- Executes tasks and emits snapshot artifacts + status.

4) Firecrawl Adapter
- Wraps Firecrawl API, enforces formats and changeTracking, applies maxAge caching.
- Logs request metadata for audit.

5) Snapshot Store
- Immutable storage of raw HTML/markdown/screenshots/PDFs.
- DocumentSnapshot metadata includes content hashes and changeTracking.

6) Extraction Service (centralized)
- Deterministic parsers + OpenAI Structured Outputs.
- Optional vision pass for photos/floorplans.
- Produces SourceObservations and FieldObservations with evidence.

7) Normalization Service
- libpostal address normalization + USPS unit designators.
- Standardizes currency, dates, lease terms, fees, amenities.

8) Dedupe / Entity Resolution Service
- Blocking + scoring + clustering into canonical Building/Unit/Listing.
- Merge policy: source trust + recency + confidence.

9) Geo / Commute Service (local-only)
- Geocoding: Pelias primary; Nominatim optional fallback.
- Routing: OTP for transit; Valhalla for walk/bike/drive (OSRM optional).
- Isochrone precompute and commute caching.

10) Ranking Service
- Hard filters -> fast scoring -> LLM rerank -> diversity rerank.
- Returns explanations and missing-info prompts.

11) Alert Service
- Matches listing changes to SearchSpecs.
- Sends local notifications or SMTP email digests (no paid SMS).

12) API + UI + SearchSpec Parser
- FastAPI endpoints for search, listing detail, compare, alerts.
- NL input -> SearchSpec parsing, validation, and storage.
- Local web UI (map/list, compare, near-miss explorer).

13) Evaluation and QA
- Golden sets, regression tests, coverage/freshness dashboards.

## End-to-end data flow
1) User NL query -> SearchSpec (hard/soft constraints, anchors).
2) Orchestrator plans tasks; Policy Gate approves/blocks.
3) Scheduler executes tasks via Firecrawl or manual import.
4) Snapshot Store persists raw artifacts + metadata.
5) Extraction Service emits SourceObservations + FieldObservations with evidence.
6) Normalization Service standardizes fields.
7) Dedupe Service creates canonical Building/Unit/Listing + ListingChanges.
8) Geo/Commute Service enriches listings and caches commute results.
9) Ranking Service retrieves candidates and returns ranked results with explanations.
10) Alert Service matches ListingChanges to SearchSpecs and notifies.

## Canonical data model (minimum)
- Source, SourcePolicy
- DocumentSnapshot (immutable; content_hash, formats, change_tracking)
- SourceObservation (extracted_json, extractor_version, validation_report)
- FieldObservation / Fact (value, confidence, evidence[])
- Building, Unit, Listing
- ListingChange (audit log)
- SearchSpec, Match, Alert

Fact/Evidence requirements:
- Every non-null field has evidence (text span or image region) and confidence.
- Conflicting values are retained with provenance.

## Acquisition and compliance (authoritative)
- Policy statuses: crawl_allowed, partner_required, manual_only, unknown.
- Manual-only sources (no automation): Craigslist, Zillow/HotPads/Trulia, Realtor.com, Apartments.com, PadMapper, Zumper, Facebook Marketplace.
- Task types: SearchTask, MapTask, CrawlTask, ScrapeTask, ExtractTask (optional), ImportTask.
- No login automation, CAPTCHA bypass, or paywall circumvention.

## Geo and commute (local-only)
- OSM + DataSF layers stored locally; no paid APIs.
- OTP + GTFS (respect agency licensing; 511 GTFS is local-only, non-redistributable).
- Commute cache keys: (origin_h3, anchor_id, mode, time_bucket); TTL by mode.

## Ranking and retrieval
- Candidate retrieval via Postgres filters + Postgres FTS + pgvector.
- Hard filters with probabilistic checks for uncertain fields.
- Fast utility scoring, then LLM rerank, then diversity rerank (MMR/xQuAD).
- Near-miss pool with explicit tradeoffs.

## Storage and deployment
- Postgres + PostGIS is source of truth; pgvector extension for embeddings.
- Redis for queues and short-lived caches.
- Object store: filesystem or MinIO.
- Services run locally and bind to localhost.

## MVP scope (weeks 0-2)
- Source registry + policy gating.
- Firecrawl crawl/scrape on 10-30 crawl_allowed PM sites.
- Extraction v1 + normalization + basic dedupe.
- Postgres + PostGIS + pgvector.
- Simple UI + daily email digest alerts.

## Open questions
1) Queue system choice (Redis/RQ vs Celery vs Postgres-based queue).
2) Routing engine secondary option (run OSRM alongside Valhalla or Valhalla only).
3) UI scope (minimal vs full SPA).
4) Use of 511 GTFS feeds given licensing restrictions (local-only vs avoid 511 RT).
5) Object storage (filesystem vs MinIO).
6) Evidence storage shape (JSONB-only vs normalized FieldObservations table).
