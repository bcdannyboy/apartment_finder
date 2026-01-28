# Phase Contracts

## Phase 1

### Test Summary
- Coverage: Policy Gate decision matrix, ImportTask enforcement for manual_only, Snapshot Store immutability, Evidence linking, Postgres PostGIS pgvector migrations, determinism, and local-only binding.
- Compliance: blocked automation paths for login, CAPTCHA bypass, and paywall circumvention.
- Reference: _dev_docs/agent_reports/phase_tests_phase1.md

## Phase 2 - Acquisition Pipeline

### Test Summary
- Test plan: _dev_docs/agent_reports/phase_tests_phase2.md
- Coverage: task schema and queue payload validation, Policy Gate enforcement, per-domain rate limits and politeness, Firecrawl adapter format rules with changeTracking and content_hash fallback, manual-only enforcement, audit logging completeness, error handling with policy-aware retries, deterministic scheduling inputs.
- Hard constraints and evidence model: same as Phase 1, with required evidence artifacts for every test case.

## Phase 3

### Test Summary
- Test plan: _dev_docs/agent_reports/phase_tests_phase3.md
- Coverage: deterministic pre-extraction, Structured Outputs schema validation, evidence requirements, ambiguity handling, validation_report behavior, normalization preservation, evidence locator validity, and determinism and replay on frozen snapshots.
- Tests inherit Phase 1 hard constraints and the evidence model.

## Phase 4 - Entity Resolution and Canonicalization

### Test Summary
- Test plan: _dev_docs/agent_reports/phase_tests_phase4.md
- Coverage: blocking and scoring reproducibility, threshold band enforcement, merge policy ordering (trust, recency, confidence), conflict retention with provenance, ListingChange correctness and idempotency, and determinism for fixed inputs.

## Phase 5 - Geo and Commute Enrichment

### Test Summary
- Test plan: _dev_docs/agent_reports/phase_tests_phase5.md
- Coverage: local-only geocoding and routing (Pelias primary, Nominatim fallback), OTP for transit, Valhalla for walk/bike/drive, commute cache key shape, determinism and cache usage, geocode precision and confidence fields, and 511 GTFS local storage and graph rebuild behavior.

## Phase 6

### Test Summary
- Test plan: _dev_docs/agent_reports/phase_tests_phase6.md
- Coverage: SearchSpec validation and schema versioning, Postgres FTS + pgvector retrieval only, confidence-aware hard filters, LLM rerank inputs limited to structured fields and evidence, diversity caps by building and neighborhood, API schema stability, and deterministic outputs.

## Phase 7

### Test Summary
- Test plan: _dev_docs/agent_reports/phase_tests_phase7.md
- Coverage: matching logic vs ranking hard constraints, ListingChange triggers and idempotency, dispatch logging correctness and immutability, local notification and SMTP-only enforcement, and alert error handling and retry rules.

## Phase 8

### Test Summary
- Test plan: _dev_docs/agent_reports/phase_tests_phase8.md
- Coverage: UI uses API only, evidence surfaced in detail and history views, change history ordering with evidence links, compare and near-miss input validation, deterministic regression suite on frozen snapshots, and evaluation metric sanity checks.

## Purpose
Define cross-phase service contracts and the minimum guarantees each phase provides to the next.

## References
- architecture_api_contracts.md
- architecture_schema.md
- architecture_evidence.md
- architecture_searchspec.md
- architecture_tasks_queue.md

## Contract Surfaces
- Policy Gate API
- Snapshot Store API
- Ranking API
- Alert API

## Contract Quality Gates
- Schema compatibility and versioning rules
- Error handling and retry guidance
- Idempotency and immutability guarantees
- Evidence and provenance requirements

## Integration Tests
- Test plan: _dev_docs/agent_reports/phase_tests_integration.md
- Coverage: full pipeline and contract boundaries across phases.
- Contract tests for Policy Gate, Snapshot Store, Ranking API, and Alert API.
- Network egress restricted to Firecrawl and OpenAI endpoints only.
- Determinism and snapshot immutability enforced in cross-phase runs.

## Notes
This document focuses on interface guarantees; implementation details live in service specs.
