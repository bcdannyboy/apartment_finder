# Apartment Finder High-Level Component Spec (Verbose)

## Purpose
This document expands the component catalog into explicit responsibilities, inputs, outputs, and invariants. It complements the phase contracts by focusing on module boundaries and data flow.

## Authoritative companion docs
- architecture_decisions_and_naming.md
- architecture_schema.md
- architecture_evidence.md
- architecture_api_contracts.md
- architecture_searchspec.md
- architecture_tasks_queue.md
- architecture_retrieval.md
- architecture_geo_commute.md
- architecture_compliance_enforcement.md
- architecture_traceability_matrix.md

## Global constraints and invariants
- Local-first system; Docker OK; services bind to localhost.
- Only paid services: Firecrawl and OpenAI.
- Compliance gating is mandatory before any automated fetch.
- DocumentSnapshots are immutable; Facts require evidence and confidence for all non-null values.
- Evidence is stored in a normalized Evidence table linked to Facts.
- Python is the core language.

## Component catalog

### 1) Source Registry and Policy Gate
Responsibilities:
- Store source metadata and compliance policy records.
- Expose a decision API for acquisition tasks.
- Enforce allowed_operations by policy_status.

Inputs:
- Source definitions (name, base_domains, kind).
- Robots.txt and ToS metadata (stored as snapshots).

Outputs:
- Policy decisions (allow/deny with reason).
- Versioned policy records for audit.

Invariants:
- manual_only sources permit ImportTask only.
- unknown and partner_required deny automation.

Interfaces:
- Policy Gate API contract (see phase contracts).

### 2) Acquisition Orchestrator
Responsibilities:
- Translate SearchSpecs and seed lists into tasks.
- Schedule discovery sweeps and targeted crawls.
- Create tasks that are policy-compliant by design.

Inputs:
- SearchSpecs; manual seed lists; crawl stats.
- Source Registry and Policy Gate.

Outputs:
- SearchTask, MapTask, CrawlTask, ScrapeTask, ImportTask.

Invariants:
- No automated tasks for unknown or manual_only sources.
- Discovery outputs create new sources with policy_status = unknown until reviewed.

### 3) Scheduler / Queue / Workers
Responsibilities:
- Enforce per-domain politeness and rate limits.
- Retry on transient errors with backoff.
- Execute acquisition tasks and emit snapshots.
- Redis + RQ for queueing and worker orchestration.

Inputs:
- Task records; rate_limits.

Outputs:
- DocumentSnapshots and execution status events.

Invariants:
- Per-domain queues enforced; rate limits never exceeded.
- No login automation or CAPTCHA bypass.

### 4) Firecrawl Adapter
Responsibilities:
- Wrap Firecrawl Search, Map, Crawl, Scrape.
- Apply standard formats and changeTracking rules.
- Record request metadata for audit.

Inputs:
- Task payloads and adapter config.

Outputs:
- Raw artifacts and Firecrawl metadata for DocumentSnapshot.

Invariants:
- changeTracking requires markdown plus changeTracking object.
- content_hash fallback is required if changeTracking missing.

### 5) Snapshot Store
Responsibilities:
- Persist immutable raw artifacts.
- Provide references for downstream extraction and reprocessing.

Inputs:
- Raw artifacts (html, markdown, screenshots, pdfs).

Outputs:
- raw_refs and DocumentSnapshot metadata.

Invariants:
- Artifacts are immutable; new fetch creates a new snapshot_id.

### 6) Extraction Service
Responsibilities:
- Deterministic parsing and OpenAI Structured Outputs.
- Produce SourceObservations and Facts with evidence.

Inputs:
- DocumentSnapshots and raw artifacts.

Outputs:
- SourceObservations, Facts, validation_report.

Invariants:
- All non-null fields must have evidence and confidence.
- Ambiguous fields return multiple candidates, not guesses.

### 7) Normalization Service
Responsibilities:
- Normalize address, unit designators, currency, dates, lease terms, fees, amenities.

Inputs:
- Facts and SourceObservations.

Outputs:
- Normalized Facts and standardized values.

Invariants:
- Raw values are preserved alongside normalized values.

### 8) Dedupe / Entity Resolution Service
Responsibilities:
- Blocking, scoring, clustering into canonical entities.
- Merge policy based on source trust, recency, confidence.

Inputs:
- Normalized Facts and SourceObservations.

Outputs:
- Canonical Building, Unit, Listing and ListingChange records.

Invariants:
- Conflicts retained with provenance; no deletion of Facts.

### 9) Geo / Commute Service (local-only)
Responsibilities:
- Local geocoding, routing, and commute caching.
- Load open data layers into PostGIS.

Inputs:
- Canonical listings and normalized addresses.
- OSM and DataSF layers; GTFS feeds.

Outputs:
- Geocode Facts with precision and confidence.
- Commute cache keyed by (origin_h3, anchor_id, mode, time_bucket).

Invariants:
- No paid geocoding or routing APIs.
- 511 GTFS stored locally and not redistributed.
- Walk/bike/drive routing uses Valhalla primary; OSRM may be used as a secondary option.

### 10) Ranking Service
Responsibilities:
- Candidate retrieval and ranking pipeline.
- Generate explanations, missing-info prompts, near-miss pool.

Inputs:
- SearchSpecs; canonical listings; Facts; commute data.

Outputs:
- Ordered results with explanation metadata.

Invariants:
- LLM rerank uses only structured fields and evidence.
- Diversity caps enforced by building, neighborhood, source.

### 11) Alert Service
Responsibilities:
- Match ListingChange events to SearchSpecs.
- Dispatch local notifications or SMTP email.

Inputs:
- ListingChange events; SearchSpecs.

Outputs:
- Alert records and dispatch logs.

Invariants:
- No paid SMS or external messaging APIs.

### 12) API + UI + SearchSpec Parser
Responsibilities:
- FastAPI endpoints for search, listing detail, compare, alerts.
- SearchSpec parser from NL input.
- Local web UI (full SPA) for map/list, detail, compare, near-miss, alerts.

Inputs:
- SearchSpecs; ranking outputs; listing data.

Outputs:
- API responses and UI views.

Invariants:
- UI uses API only; no direct DB access.

### 13) Evaluation and QA
Responsibilities:
- Golden sets, regression tests, dashboards.

Inputs:
- Frozen snapshots; canonical data; ranking outputs.

Outputs:
- Metrics reports and regression gates.

Invariants:
- Evaluation runs are deterministic for fixed inputs.

## Key data flows

### DocumentSnapshot flow
1) Acquisition task produces raw snapshot.
2) Snapshot stored in object store; metadata in document_snapshots.
3) Extraction Service produces SourceObservations linked to snapshot_id.

### Canonicalization flow
1) Normalization applies to Facts and SourceObservations.
2) Dedupe clusters observations into canonical entities.
3) ListingChange records record canonical updates.

### Ranking flow
1) User NL query -> SearchSpec.
2) Hard filters applied via SQL and confidence checks.
3) Fast scoring, LLM rerank, diversity rerank.
4) Explanations and near-miss pool returned.

### Alert flow
1) ListingChange emitted.
2) Alert Service matches SearchSpecs.
3) Alerts delivered via local notifications or SMTP.

## Storage schema outline (expanded)
Core tables:
- sources
- source_policies
- document_snapshots
- source_observations
- facts
- evidence
- fact_evidence
- buildings
- units
- listings
- listing_changes
- search_specs
- matches
- alerts

Key indexes:
- listings on price, beds, baths, neighborhood
- listings on geometry (PostGIS)
- document_snapshots on url, content_hash
- facts on field_path
- source_observations on snapshot_id, source_id

## CLI and runtime workflow
The CLI provides local orchestration without external dependencies.
- apf ingest --source <id>
- apf extract --since <ts>
- apf normalize --since <ts>
- apf dedupe --since <ts>
- apf geo-sync
- apf rank --spec <id>
- apf alerts
- apf eval

Runtime workflow:
1) Scheduler generates tasks.
2) Workers fetch snapshots (Firecrawl or manual).
3) Extraction and normalization run on new snapshots.
4) Dedupe updates canonical listings and change history.
5) Geo/commute service enriches listings.
6) Ranking and alerts update UI and notifications.
