# Apartment Finder (Local-First)

## Overview
Apartment Finder is a local-first system for discovering, extracting, and ranking San Francisco rental listings under strict compliance rules. It prioritizes provenance, evidence-backed data, and a reproducible pipeline from acquisition to ranking and alerts.

## Hard constraints
- Local-first system; Docker OK; services bind to localhost.
- Only paid services: Firecrawl and OpenAI.
- Strict compliance gating: only crawl sources with policy_status = crawl_allowed; restricted portals are manual-only unless licensed.
- Provenance-first data model: immutable snapshots and evidence + confidence required for all non-null fields.
- Python is the core language.
- No login automation, CAPTCHA bypass, or paywall circumvention.

## Resolved decisions
- Queue system: Redis + RQ.
- Routing engine: OpenTripPlanner for transit; Valhalla for walk/bike/drive.
- UI scope: full SPA.
- GTFS: use 511 GTFS with local storage and no redistribution.
- Object storage: filesystem.
- Evidence storage: normalized Evidence table with fact_evidence links.

## What this system does
- Discovers crawl-allowed property manager and building sites.
- Captures immutable snapshots of listing pages.
- Extracts structured data with evidence and confidence.
- Normalizes and deduplicates listings into canonical entities.
- Enriches listings with local-only geo and commute data.
- Ranks results with explanations and near-miss reasoning.
- Sends local notifications or SMTP email alerts.

## What this system does not do
- Automated crawling of restricted portals unless licensed.
- Use of any paid API beyond Firecrawl and OpenAI.
- Cloud hosting or multi-tenant deployment.

## Core documents
- architecture_source_of_truth.md
- architecture_kickoff.md
- architecture_components.md
- _dev_docs/agent_reports/07_phase_contracts.md
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

## Non-authoritative research notes
- _dev_docs/apt_judge.md and _dev_docs/apt_juror_* are research notes and are superseded by architecture_source_of_truth.md and architecture_decisions_and_naming.md when conflicts exist.

## System components (summary)
- Source Registry and Policy Gate
- Acquisition Orchestrator
- Scheduler / Queue / Workers (Redis + RQ)
- Firecrawl Adapter
- Snapshot Store
- Extraction Service
- Normalization Service
- Dedupe / Entity Resolution Service
- Geo / Commute Service (local-only)
- Ranking Service
- Alert Service
- API + full SPA UI + SearchSpec Parser
- Evaluation and QA

## Data model (summary)
- DocumentSnapshot: immutable raw artifact with content_hash.
- SourceObservation: extraction output linked to a snapshot.
- Fact: field value with evidence and confidence.
- Evidence: normalized table linked to Facts.
- fact_evidence: join table linking Facts to Evidence.
- Canonical entities: Building, Unit, Listing.
- ListingChange: canonical change history.
- SearchSpec, Match, Alert.

## Compliance model (summary)
- Every automated task requires Policy Gate approval.
- Manual-only sources allow ImportTask only.
- No login automation, CAPTCHA bypass, or paywall circumvention.

## Local-first deployment
- Postgres + PostGIS + pgvector.
- Redis for queues and short-lived caches.
- Object store (filesystem).
- Local services: Pelias, OpenTripPlanner, Valhalla.

## Getting started
This repository is currently architecture-first. Implementation will follow the phase contracts and component specifications. See the core documents listed above for details.

Local data platform setup (Postgres + PostGIS + pgvector, Redis + RQ, local-only networking, and egress allowlist) is documented in `LOCAL_SETUP.md`.
