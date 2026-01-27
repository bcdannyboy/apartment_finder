# Apartment Finder High-Level Component Spec

This document defines the major components/modules, their responsibilities, interfaces, and data flow. It is intended to guide implementation planning and task allocation.

---

## 1) Services/modules and responsibilities

### 1.1 Source Registry and Policy Gate
- Stores per-domain policy classification and compliance metadata.
- Provides a single policy-check API to all acquisition tasks.
- Blocks any task if policy is not `crawl_allowed` or `manual_only` (for imports).

### 1.2 Acquisition Orchestrator
- Plans searches and sweep grids.
- Generates Search/Map/Crawl/Scrape/Import tasks.
- Enforces per-domain budgets and cadence.

### 1.3 Firecrawl Adapter
- Single module that wraps Firecrawl API calls.
- Enforces standard formats, changeTracking, caching.
- Logs request metadata for audit.

### 1.4 Snapshot Store
- Immutable storage of raw HTML, markdown, screenshots, PDFs.
- Provides references for provenance and reprocessing.

### 1.5 Extraction Service
- Deterministic parser for known fields.
- OpenAI Structured Outputs extraction for full schema.
- Produces SourceObservation records with evidence.

### 1.6 Normalization Service
- Address normalization (libpostal + USPS unit designators).
- Standardizes currencies, dates, lease terms, fees, amenities.

### 1.7 Dedupe / Entity Resolution Service
- Blocking + scoring pipeline.
- Clustering into canonical Building/Unit/Listing.
- Merge policy: source trust + recency + confidence.

### 1.8 Geo/Commute Service
- Local geocoding (Pelias/Nominatim).
- OTP routing for transit; Valhalla/OSRM for walk/bike/drive.
- Isochrone precompute and commute caching.

### 1.9 Ranking Service
- Hard filters -> fast scoring -> LLM rerank -> diversity rerank.
- Generates explanations and missing-info prompts.

### 1.10 Alert Service
- Matches change events to SearchSpecs.
- Sends local notifications or SMTP email digests.

### 1.11 API + UI
- FastAPI endpoints for search, listing detail, compare, alerts.
- Local web UI (map/list, compare, near-miss explorer).

### 1.12 Evaluation and QA
- Golden set runner.
- Regression tests for extraction, dedupe, ranking.
- Coverage and freshness dashboards.

---

## 2) Interfaces and key data flows

### 2.1 DocumentSnapshot flow
1. Acquisition task produces raw snapshot.
2. Snapshot stored in object store; metadata in `document_snapshots` table.
3. Extraction Service produces `source_observations` linked to snapshot.

### 2.2 Canonicalization flow
1. Normalization applies to observations.
2. Dedupe service clusters observations into canonical entities.
3. Canonical `listing` records updated and changes logged.

### 2.3 Ranking flow
1. User NL query -> SearchSpec.
2. Hard filters applied in SQL.
3. Fast scorer computes utility.
4. LLM rerank top-N.
5. Diversity rerank and final result set returned.

### 2.4 Alert flow
1. Listing change event created.
2. Alert service checks SearchSpecs.
3. Alerts emitted to email or local notifications.

---

## 3) Storage schema outline

### Core tables
- `sources`
- `source_policies`
- `document_snapshots`
- `source_observations`
- `buildings`
- `units`
- `listings`
- `listing_changes`
- `facts` (optional normalized field-level provenance)
- `search_specs`
- `matches`
- `alerts`

### Key indexes
- `listings` on price, beds, baths, neighborhood
- `listings` on geometry (PostGIS)
- `document_snapshots` on url, content_hash
- `facts` on field_path
- `source_observations` on source_id, snapshot_id

---

## 4) CLI / orchestration and runtime workflow

### CLI commands (initial plan)
- `apf ingest --source <id>`: run acquisition tasks.
- `apf extract --since <ts>`: extract new snapshots.
- `apf normalize --since <ts>`: normalize extracted fields.
- `apf dedupe --since <ts>`: run entity resolution.
- `apf geo-sync`: update geocodes and commute caches.
- `apf rank --spec <id>`: run ranking pipeline.
- `apf alerts`: send alerts for new/changed listings.
- `apf eval`: run golden set regression tests.

### Runtime workflow
1. Scheduler generates tasks.
2. Workers fetch snapshots (Firecrawl/manual).
3. Extraction + normalization run on new snapshots.
4. Dedupe updates canonical listings.
5. Geo/commute service enriches listings.
6. Ranking and alerts update UI and notifications.

