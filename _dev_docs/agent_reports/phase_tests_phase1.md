# Phase 1 Test Plan (Core Data Contracts and Policy Gate)

## References
- architecture_decisions_and_naming.md
- architecture_schema.md
- architecture_evidence.md
- architecture_api_contracts.md
- architecture_compliance_enforcement.md


## Overview
- Goal: validate Phase 1 core data contracts, Policy Gate decisions, Snapshot Store behavior, and evidence provenance under strict compliance gating.
- Constraints: local-first execution, services bind to localhost, only paid services are Firecrawl and OpenAI, Python core services, no login automation, no CAPTCHA bypass, and no paywall circumvention.
- Data model: Facts must link to Evidence via the normalized Evidence table and the fact_evidence join table.
- Environment: Postgres with PostGIS and pgvector enabled; Snapshot Store backed by local storage; Policy Gate and Snapshot Store APIs running on localhost only.

## Test Matrix
| ID | Area | Setup | Action | Expected |
| --- | --- | --- | --- | --- |
| PGATE-001 | Policy Gate | Source classified as crawl_allowed | Submit policy check | Decision is crawl_allowed and automation path is permitted |
| PGATE-002 | Policy Gate | Source classified as manual_only | Submit policy check | Decision is manual_only and ImportTask is required |
| PGATE-003 | Policy Gate | Source classified as partner_required | Submit policy check | Decision is partner_required and automation is blocked |
| PGATE-004 | Policy Gate | Source classified as unknown | Submit policy check | Decision is unknown and automation is blocked |
| IMP-001 | ImportTask | manual_only source | Request ingestion | ImportTask is created and only manual workflow is used |
| DB-001 | Migrations | Fresh Postgres | Apply migrations | Postgres extensions PostGIS and pgvector are enabled |
| DB-002 | Migrations | Existing schema | Re-apply migrations | No data loss; migrations are idempotent |
| SNAP-001 | Snapshot Store | New raw content | Create snapshot | content_hash computed and stored |
| SNAP-002 | Snapshot Store | Snapshot exists | Re-fetch same content | New snapshot row is created; prior snapshot unchanged |
| SNAP-003 | Snapshot Store | Snapshot exists | Fetch by raw_refs | raw_refs are immutable and map to stored snapshot |
| EVID-001 | Evidence | Fact without Evidence | Persist Fact | Rejected; Fact requires Evidence linkage |
| EVID-002 | Evidence | Evidence + Fact | Persist Fact and Evidence | fact_evidence link is created and valid |
| API-001 | Policy Gate API | Valid request | Call API | Response schema matches contract and decision enum |
| API-002 | Snapshot Store API | Valid snapshot request | Call API | Response schema matches contract and includes content_hash |
| LOCAL-001 | Local binding | Services running | Inspect listeners | All services bind to 127.0.0.1 or localhost only |
| DET-001 | Determinism | Same inputs | Repeat runs | Same outputs and hashes; no drift |

## Negative Tests
- Blocked automation: attempts to automate manual_only sources are denied and logged as policy violations.
- No login automation: attempts to submit credentials, automate login flows, or store session cookies are blocked.
- No CAPTCHA bypass: any attempt to bypass or solve CAPTCHA is blocked and recorded as disallowed.
- No paywall circumvention: attempts to access paywalled content via automation are blocked.
- External services: attempts to call paid services other than Firecrawl or OpenAI are rejected.
- Local-first enforcement: attempts to bind services to non-local addresses are rejected.

## Contract Tests
- Policy Gate API contract: request includes source metadata and policy context; response includes decision enum (crawl_allowed, manual_only, partner_required, unknown), required reason fields, and compliance flags.
- Policy Gate error handling: invalid source metadata returns validation errors without side effects.
- Snapshot Store API contract: create, fetch, and list endpoints return stable schemas with content_hash, raw_refs, and immutable snapshot identifiers.
- Snapshot Store error handling: invalid raw_refs and missing snapshots return consistent error payloads.

## Determinism
- Policy Gate determinism: identical inputs always produce the same decision and reason payloads.
- Snapshot determinism: identical raw content yields the same content_hash; re-fetch creates a new snapshot with a new identifier while preserving hash.
- Idempotency: retrying Snapshot Store create and Policy Gate evaluation does not duplicate side effects beyond the expected new snapshot per re-fetch rule.

## Data Integrity
- Evidence normalization: Evidence is stored only in the normalized Evidence table; Facts link via fact_evidence only.
- Referential integrity: fact_evidence references valid Fact and Evidence rows; invalid references are rejected.
- Snapshot immutability: content_hash, raw_refs, and stored raw payloads are immutable after creation.
- Migration integrity: Postgres schema includes PostGIS and pgvector extensions and retains data across re-application.
