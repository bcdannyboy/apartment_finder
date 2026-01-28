# Apartment Finder Source of Truth Architecture

## Purpose
This document is the single source of truth for system architecture, constraints, and canonical data contracts. It is authoritative over all other architecture notes. Any conflicting proposal must be resolved in favor of this document.

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

## Hard constraints (must hold in every phase)
- Local-first system; Docker OK; services bind to localhost.
- Only paid services: Firecrawl and OpenAI.
- Strict compliance gating: only crawl sources with policy_status = crawl_allowed; restricted portals are manual-only unless licensed.
- Provenance-first data model: immutable snapshots and evidence + confidence required for all non-null fields.
- Python is the core language.
- No login automation, CAPTCHA bypass, or paywall circumvention.

## Non-goals
- Automated scraping of restricted portals unless licensed.
- Use of any paid API beyond Firecrawl and OpenAI.
- Cloud-hosted or multi-tenant deployment.
- Bypassing robots.txt, paywalls, or access restrictions.

## System goals (operational)
- Maximum compliant coverage of San Francisco rental inventory, especially long-tail property manager and building sites.
- High freshness and change detection for crawl-allowed sources.
- Provenance-first extraction that can be audited and reprocessed.
- Decision-grade ranking with explanations, near-miss reasoning, and diversity controls.
- Local privacy: user data and listing corpus remain on the local machine.

## Core components (authoritative list)
1) Source Registry and Policy Gate
- Stores per-source policy classification and compliance metadata.
- Provides a single policy-check API to all acquisition tasks.
- Blocks any automation unless policy_status = crawl_allowed.
- Allows ImportTask only for manual_only sources.

2) Acquisition Orchestrator
- Plans searches and sweep grids.
- Generates SearchTask, MapTask, CrawlTask, ScrapeTask, ImportTask.
- Enforces per-domain budgets and cadence.

3) Scheduler / Queue / Workers
- Runs per-domain queues with politeness limits.
- Applies adaptive cadence, retries, and backoff.
- Executes tasks and emits snapshot artifacts and status.
 - Redis + RQ for queueing and worker orchestration.

4) Firecrawl Adapter
- Wraps Firecrawl API calls.
- Enforces standard formats, changeTracking requirements, and caching settings.
- Logs request metadata for audit.

5) Snapshot Store
- Immutable storage of raw HTML, markdown, screenshots, PDFs.
- DocumentSnapshot metadata includes content hashes and changeTracking metadata.

6) Extraction Service (centralized)
- Deterministic parsers plus OpenAI Structured Outputs.
- Optional vision pass for photos and floorplans.
- Produces SourceObservations and Facts with evidence.

7) Normalization Service
- libpostal address normalization and USPS unit designators.
- Standardizes currency, dates, lease terms, fees, amenities.

8) Dedupe / Entity Resolution Service
- Blocking, scoring, and clustering into canonical Building, Unit, Listing.
- Merge policy: source trust + recency + confidence.
- Conflicts retained with provenance.

9) Geo / Commute Service (local-only)
- Geocoding: Pelias primary; Nominatim optional fallback (self-hosted only).
- Routing: OpenTripPlanner for transit; Valhalla for walk/bike/drive.
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
- Local web UI (full SPA: map/list, compare, near-miss explorer).

13) Evaluation and QA
- Golden sets, regression tests, coverage and freshness dashboards.

## End-to-end data flow (authoritative)
1) User NL query -> SearchSpec (hard/soft constraints, anchors, tradeoffs).
2) Orchestrator plans tasks; Policy Gate approves or blocks.
3) Scheduler executes tasks via Firecrawl or manual import.
4) Snapshot Store persists raw artifacts and metadata (immutable).
5) Extraction Service emits SourceObservations and Facts with evidence.
6) Normalization Service standardizes extracted fields.
7) Dedupe Service creates canonical Building, Unit, Listing and ListingChange history.
8) Geo/Commute Service enriches listings and caches commute results.
9) Ranking Service retrieves candidates and returns ranked results with explanations.
10) Alert Service matches ListingChanges to SearchSpecs and notifies users.

## Canonical data model (minimum)
- Source, SourcePolicy
- DocumentSnapshot (immutable; content_hash, formats, change_tracking)
- SourceObservation (extracted_json, extractor_version, validation_report)
- Fact (field_path, value_json, confidence)
- Evidence (snapshot_id, kind, locator, excerpt)
- fact_evidence (fact_id, evidence_id, rank)
- Building, Unit, Listing
- ListingChange (audit log)
- SearchSpec, Match, Alert

### Fact and Evidence requirements
- Every non-null field has evidence (text span or image region) and confidence.
- Evidence is stored in the Evidence table and linked to Facts via fact_evidence.
- Conflicting values are retained with provenance; canonicalization does not delete facts.

## Acquisition and compliance (authoritative)
- Policy statuses: crawl_allowed, partner_required, manual_only, unknown.
- Manual-only sources (no automation): Craigslist, Zillow/HotPads/Trulia, Realtor.com, Apartments.com, PadMapper, Zumper, Facebook Marketplace.
- Task types: SearchTask, MapTask, CrawlTask, ScrapeTask, ImportTask.
- No login automation, CAPTCHA bypass, or paywall circumvention.

### Compliance enforcement
- Policy Gate checks are mandatory before any automated task.
- Unknown and partner_required sources are denied until reviewed.
- Manual-only sources accept ImportTask only.

### Firecrawl usage rules (architectural)
- changeTracking requires markdown plus a changeTracking object.
- changeTracking may be missing; content_hash fallback is required.
- Search and Map are discovery tools only, not exhaustive coverage.
- Crawl results must be captured immediately; do not rely on remote retention.

## Geo and commute (local-only)
- OSM and DataSF layers stored locally; no paid APIs.
- OTP for transit; Valhalla for walk/bike/drive; OSRM allowed as a secondary option.
- Commute cache keys: (origin_h3, anchor_id, mode, time_bucket).
- GTFS feeds stored locally; 511 GTFS requires API token and must not be redistributed.

## Ranking and retrieval
- Candidate retrieval via Postgres filters + Postgres FTS + pgvector.
- Hard filters are probabilistic when field confidence is low.
- Ranking stages: fast scoring -> LLM rerank -> diversity rerank.
- Near-miss pool includes tradeoff explanation.

## Storage and deployment
- Postgres + PostGIS is the system of record; pgvector for embeddings.
- Redis for queues and short-lived caches (RQ).
- Object store: filesystem.
- Services run locally and bind to localhost.

## Initial functional scope (phase-based)
- Source registry and policy gating.
- Firecrawl crawl/scrape on crawl_allowed property manager sites.
- Extraction and normalization with evidence-first Facts.
- Basic dedupe and canonical listings.
- Postgres + PostGIS + pgvector.
- Simple UI and email digest alerts.

## Resolved decisions (authoritative)
- Queue system: Redis + RQ.
- Routing engine: Valhalla for walk/bike/drive; OpenTripPlanner for transit; OSRM allowed as secondary option.
- UI scope: full SPA.
- GTFS: use 511 GTFS with local storage and no redistribution.
- Object storage: filesystem.
- Evidence storage: normalized Evidence table with fact_evidence links.
