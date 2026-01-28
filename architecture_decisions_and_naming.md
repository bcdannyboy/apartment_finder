# Architecture Decisions and Naming (Authoritative)

## Purpose
This document defines the authoritative decisions and the canonical naming registry for entities, services, tables, enums, and constraints. It is subordinate to architecture_source_of_truth.md and resolves naming ambiguity across the repo.

## Authoritative decisions (locked)
- Paid services: OpenAI and Firecrawl only.
- Local-first system; services bind to localhost; Docker is allowed.
- Compliance gating is mandatory; automation only when policy_status = crawl_allowed.
- Manual-only sources allow ImportTask only; restricted portals are manual-only unless licensed.
- Provenance-first model: immutable DocumentSnapshot; every non-null field requires evidence and confidence.
- Evidence is normalized in Evidence and linked via fact_evidence.
- Python is the core language.
- No login automation, CAPTCHA bypass, or paywall circumvention.
- Geo and routing are local-only: Pelias primary, Nominatim optional fallback, OpenTripPlanner for transit, Valhalla for walk/bike/drive; OSRM is allowed as a secondary option for walk/bike/drive.
- 511 GTFS is desired; stored locally and not redistributed.
- Retrieval: Postgres filters + Postgres FTS + pgvector only.
- Alerts: local notifications or SMTP only.
- Queue: Redis + RQ.
- Object store: filesystem.
- UI: full SPA.

## Canonical entity names (domain level)
- Source
- SourcePolicy
- DocumentSnapshot
- SourceObservation
- Fact
- Evidence
- fact_evidence (join table)
- Building
- Unit
- Listing
- ListingChange
- SearchSpec
- Match
- Alert
- Task
- AuditLog

## Canonical table names (snake_case)
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
- tasks
- audit_logs

## Canonical service names
- Source Registry
- Policy Gate
- Acquisition Orchestrator
- Scheduler
- Workers
- Firecrawl Adapter
- Snapshot Store
- Extraction Service
- Normalization Service
- Dedupe Service
- Geo and Commute Service
- Ranking Service
- Alert Service
- API Service
- UI (SPA)
- Evaluation and QA

## Canonical enums
- PolicyStatus: crawl_allowed | partner_required | manual_only | unknown
- TaskType: SearchTask | MapTask | CrawlTask | ScrapeTask | ImportTask
- EvidenceKind: text_span | image_region
- ListingStatus: active | pending | off_market | removed | unknown
- AlertChannel: local | smtp
- GeoProvider: pelias | nominatim
- RoutingProvider: otp | valhalla | osrm
- CommuteMode: transit | walk | bike | drive

## Constraint labels (for tests and traceability)
- CONSTRAINT_LOCAL_ONLY_BINDING
- CONSTRAINT_PAID_SERVICES_ONLY
- CONSTRAINT_COMPLIANCE_GATING
- CONSTRAINT_MANUAL_ONLY_IMPORT
- CONSTRAINT_NO_LOGIN_AUTOMATION
- CONSTRAINT_NO_CAPTCHA_BYPASS
- CONSTRAINT_NO_PAYWALL_CIRCUMVENTION
- CONSTRAINT_PROVENANCE_FIRST
- CONSTRAINT_EVIDENCE_REQUIRED
- CONSTRAINT_EVIDENCE_NORMALIZED
- CONSTRAINT_RETRIEVAL_LOCAL_ONLY
- CONSTRAINT_GEO_LOCAL_ONLY
- CONSTRAINT_ALERT_CHANNELS
- CONSTRAINT_QUEUE_REDIS_RQ
- CONSTRAINT_OBJECT_STORE_FILESYSTEM
- CONSTRAINT_UI_FULL_SPA
- CONSTRAINT_NETWORK_EGRESS_ALLOWLIST
