# Apartment Finder Architecture Kickoff

## Purpose
This document expands the source-of-truth architecture into an implementation-ready plan. It is intentionally verbose so that engineering decisions can be made without guessing intent. All requirements here must remain consistent with the source-of-truth document.

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

## Goals
1) Maximum compliant coverage of San Francisco rental inventory.
2) High freshness and rapid change detection for crawl-allowed sources.
3) Provenance-first extraction for auditability and reprocessing.
4) Decision-grade ranking with explainability and near-miss reasoning.
5) Local-first privacy and storage.
6) Open-data geo and commute modeling using local services.
7) Evaluation and QA as first-class system features.

## Non-goals
1) Automated scraping of restricted portals unless licensed.
2) Use of any paid API beyond Firecrawl and OpenAI.
3) Cloud-hosted or multi-tenant deployment.
4) Evasion of robots.txt, ToS, or access restrictions.

## Compliance posture and source policy rules
Compliance is enforced at acquisition time and is non-negotiable.

### Policy classification
Each domain is assigned one of:
- crawl_allowed
- partner_required
- manual_only
- unknown

### Domain onboarding workflow
1) Capture robots.txt and store as a DocumentSnapshot.
2) Record ToS URL and a short compliance summary.
3) Classify policy_status and allowed_operations.
4) Store policy record in the Source Registry with reviewer metadata.

### Manual-only sources
Manual-only sources are restricted portals and accept ImportTask only:
- Craigslist
- Zillow / HotPads / Trulia
- Realtor.com
- Apartments.com
- PadMapper
- Zumper
- Facebook Marketplace

### Compliance guardrails
- Policy Gate must approve every automated task.
- No login automation, CAPTCHA bypass, or paywall circumvention.
- Unknown or partner_required sources are blocked until reviewed.

## Acquisition strategy
The acquisition strategy is tiered for compliance and coverage.

### Tier A: Licensed or partner feeds (excluded by default)
- MLS/IDX/RESO and PMS/ILS feeds are partner_required.
- These are out of scope unless explicitly licensed by the user.

### Tier B: Crawl-allowed long-tail sites (primary automated acquisition)
- Property manager websites.
- Building availability pages.
- Broker sites where ToS allows automation.

### Tier C: Manual-only sources
- Restricted portals and user-provided URLs/files.
- Imported artifacts are treated as DocumentSnapshots.

## End-to-end pipeline (capture -> extract -> normalize -> dedupe -> rank -> alert)

### Capture
- Firecrawl Scrape/Crawl returns raw HTML, markdown, links, and optional screenshots.
- changeTracking requires markdown plus a changeTracking object with tag and includeTags/excludeTags.
- changeTracking may be missing; content_hash fallback is required.
- Manual imports store the artifact as a DocumentSnapshot.

### Extraction
1) Deterministic parsing for JSON-LD and regex fields.
2) OpenAI Structured Outputs for schema-locked extraction with evidence.
3) Optional vision extraction for photos and floorplans.

Requirements:
- Every non-null field includes evidence and confidence.
- Ambiguous fields return multiple candidates rather than guesses.
- Structured output validation failures are recorded and retried.

### Normalization
- Address parsing via libpostal.
- USPS unit designators normalized.
- Currency, dates, lease terms, fees, and amenities standardized.
- Raw values preserved alongside normalized values.

### Dedupe and canonicalization
- Blocking and scoring using address tokens, geohash, contact fields, and image hashes.
- Conservative thresholds to avoid false merges.
- Canonical fields selected using source trust, recency, and confidence.
- ListingChange audit log records every canonical change.

### Geo and commute (local only)
- Geocoding via self-hosted Pelias (primary) and optional self-hosted Nominatim (fallback).
- Transit routing via OpenTripPlanner and GTFS feeds.
- Walk/bike/drive routing via Valhalla; OSRM allowed as a secondary option.
- Commute caching keyed by (origin_h3, anchor_id, mode, time_bucket).
- 511 GTFS requires API token and must not be redistributed.

### Ranking
- Hard filters with confidence-aware logic.
- Fast scoring for utility and risk.
- LLM rerank using only structured fields and evidence.
- Diversity rerank to avoid same-building or same-neighborhood results.
- Near-miss pool includes explicit tradeoff reasons.

### Alerts
- ListingChange events matched against SearchSpecs.
- Delivery via local notifications or SMTP only.

## Canonical data model (summary)
- Source, SourcePolicy
- DocumentSnapshot
- SourceObservation
- Fact (value + confidence)
- Evidence (normalized table)
- fact_evidence (join table)
- Building, Unit, Listing
- ListingChange
- SearchSpec, Match, Alert

## Ranking and retrieval stack
- Postgres filters and Postgres FTS for structured and text retrieval.
- pgvector for semantic retrieval.
- No external search engine or vector database.

## Freshness and recrawl scheduling
- Per-domain queues with politeness and rate limits.
- Adaptive cadence based on observed change rates.
- changeTracking and content hashes for diff detection.

## Evaluation and QA
- Golden extraction set and dedupe pair sets.
- Ranking labels and offline metrics (NDCG, hit rate, precision/recall).
- Regression suite built on frozen snapshots.

## UI/UX system requirements
- Map/list split view with commute overlays.
- Listing detail with evidence and change history.
- Compare view for 2 to 6 listings.
- Near-miss explorer for tradeoff reasoning.
- Alerts center for triage and digest.
- Full SPA UI (authoritative).

## Local deployment architecture
- API server (FastAPI).
- Scheduler and workers (Python-based, Redis + RQ).
- Postgres + PostGIS + pgvector.
- Redis for queues and short-lived caches.
- Object store (filesystem).
- Pelias, OpenTripPlanner, and Valhalla as local services.

## Security and privacy
- All data stored locally.
- Secrets in local environment configuration.
- API bound to localhost.
- Provide a local delete-all-data command.

## Phase mapping (phase-based, no timelines)
- Phase 1: Core data contracts and Policy Gate.
- Phase 2: Acquisition pipeline and Firecrawl integration.
- Phase 3: Extraction and normalization.
- Phase 4: Dedupe and canonicalization.
- Phase 5: Geo and commute enrichment.
- Phase 6: Retrieval, ranking, SearchSpec parser, and API.
- Phase 7: Alerts and notification delivery.
- Phase 8: UI and evaluation/QA.

## Resolved decisions
- Queue system: Redis + RQ.
- Routing engine: Valhalla for walk/bike/drive; OpenTripPlanner for transit; OSRM allowed as secondary option.
- UI scope: full SPA.
- GTFS: use 511 GTFS with local storage and no redistribution.
- Object storage: filesystem.
- Evidence storage: normalized Evidence table with fact_evidence links.
